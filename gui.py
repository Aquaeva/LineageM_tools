import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, messagebox, simpledialog, Listbox
import threading
import frida
import LineageM  # 匯入我們的主邏輯
import time
import json
import math
import os
import sys
import re
import random
import subprocess
import urllib.request
import urllib.parse
import shutil
from tkinter import filedialog
import psutil # type: ignore
from overlay import Overlay

CONFIG_FILE = "config.json"

class App:
    def __init__(self, root, style):
        self.root = root
        self.style = style # Store style object../

        self.MAX_LOG_LINES = 1000
        self.base_title = "Frida 控制面板 (多開版)"
        self.root.title(self.base_title)
        self.root.geometry("575x570") # Reduced size for compact view
        self.root.resizable(True, True)
        self.process = psutil.Process(os.getpid())

        # --- 多實例管理 ---
        self.instances = {} # Key: emu_name, Value: dict of state and UI elements
        self.config = {} # Holds the entire config

        # --- 主框架 ---
        self.main_frame = ttk.Frame(root, padding="2")
        self.main_frame.pack(expand=True, fill=tk.BOTH)
        self.settings_visible = True
        self.log_visible = True
        self.main_frame.grid_rowconfigure(0, weight=1) # Notebook row
        self.main_frame.grid_rowconfigure(2, weight=1) # Log frame row
        self.main_frame.grid_columnconfigure(0, weight=1)

        # --- 分頁控制 ---
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 2))

        # --- 全域控制按鈕 ---
        self.global_controls_frame = ttk.Frame(self.main_frame)
        self.global_controls_frame.grid(row=1, column=0, sticky="ew", pady=(2,0))
        
        self.save_all_button = ttk.Button(self.global_controls_frame, text="儲存所有設定", command=self.save_config, style='Taller.TButton')
        self.save_all_button.pack(side=tk.LEFT, padx=(0, 0))

        # --- 全域樣式設定 ---
        style_settings_frame = ttk.Frame(self.global_controls_frame)
        style_settings_frame.pack(side=tk.LEFT, padx=(5, 0))
        
        ttk.Label(style_settings_frame, text="按鈕高度:").pack(side=tk.LEFT)
        self.button_padding_entry = ttk.Entry(style_settings_frame, width=5)
        self.button_padding_entry.pack(side=tk.LEFT, padx=(5,0))
        
        self.apply_style_button = ttk.Button(style_settings_frame, text="套用", command=self.apply_custom_styles, style='Taller.TButton')
        self.apply_style_button.pack(side=tk.LEFT, padx=(5,0))

        ttk.Label(style_settings_frame, text="日誌高度:").pack(side=tk.LEFT, padx=(10, 0))
        self.log_height_entry = ttk.Entry(style_settings_frame, width=5)
        self.log_height_entry.pack(side=tk.LEFT, padx=(5,0))

        # --- 全域日誌輸出區域 ---
        self.log_frame = ttk.LabelFrame(self.main_frame, padding="0") # Removed text property
        self.log_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 0))
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_rowconfigure(1, weight=1) # Log area is on row 1

        # Custom title bar for the log frame
        log_title_frame = ttk.Frame(self.log_frame)
        log_title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 2))

        ttk.Label(log_title_frame, text="全域日誌輸出").pack(side=tk.LEFT)
        
        self.toggle_view_button = ttk.Button(log_title_frame, text="隱藏設定區", command=self.toggle_view, style='Taller.TButton')
        self.toggle_view_button.pack(side=tk.RIGHT)

        self.toggle_log_button = ttk.Button(log_title_frame, text="隱藏日誌", command=self.toggle_log_view, style='Taller.TButton')
        self.toggle_log_button.pack(side=tk.RIGHT, padx=(0, 5))

        self.clear_log_button = ttk.Button(log_title_frame, text="清除日誌", command=self.clear_log, style='Taller.TButton')
        self.clear_log_button.pack(side=tk.RIGHT, padx=(0, 5))

        self.log_area = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, state='disabled', height=8)
        self.log_area.grid(row=1, column=0, sticky="nsew")

        # --- 初始化 ---
        self.log_message("--- 初始化 ---")
        self.log_message(f"Frida 版本: {frida.__version__}")
        self.load_and_create_tabs()
        
        # --- 環境自檢 ---
        adb_path = self.get_first_adb_path()
        self.list_running_emulators(adb_path)
        self.list_adb_forwards(adb_path)
        LineageM.list_frida_devices(logger=self.log_message)

        self.log_message("---------------")
        self.log_message("請在各分頁點擊 '連接' 按鈕來附加到目標進程。")


        # self.root.bind('<Configure>', self.update_title_with_size) # Removed
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.update_stats_in_title() # Start periodic title updates
    
    def update_stats_in_title(self):
        try:
            mem_info = self.process.memory_info()
            mem_mb = mem_info.rss / (1024 * 1024)  # RSS in MB
            thread_count = threading.active_count()
            width = self.root.winfo_width()
            height = self.root.winfo_height()

            new_title = (f"{self.base_title} | "
                         f"記憶體: {mem_mb:.2f} MB | "
                         f"執行緒: {thread_count} | "
                         f"[{width}x{height}]")

            if self.root.title() != new_title:
                self.root.title(new_title)
        except (psutil.NoSuchProcess, tk.TclError):
            # Process or window might be gone during shutdown
            return
        
        # Schedule the next update
        self.root.after(2000, self.update_stats_in_title)

    def toggle_view(self):
        if self.settings_visible:
            # Hide settings
            self.notebook.grid_remove()
            self.global_controls_frame.grid_remove()
            self.main_frame.grid_rowconfigure(0, weight=0) # Collapse notebook row
            self.toggle_view_button.config(text="顯示設定區")
            self.root.geometry("575x350") # Shrink window
            self.settings_visible = False
        else:
            # Show settings
            self.notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 2))
            self.global_controls_frame.grid(row=1, column=0, sticky="ew", pady=(2,0))
            self.main_frame.grid_rowconfigure(0, weight=1) # Expand notebook row
            self.toggle_view_button.config(text="隱藏設定區")
            self.root.geometry("575x570") # Expand window
            self.settings_visible = True

    def toggle_log_view(self):
        if self.log_visible:
            # Hide log
            self.log_area.grid_remove()
            self.log_frame.grid_rowconfigure(1, weight=0)
            self.main_frame.grid_rowconfigure(2, weight=0) # Collapse log frame row in main frame
            self.toggle_log_button.config(text="顯示日誌")
            self.log_visible = False
            self.root.geometry("575x420") # Removed to let notebook expand
        else:
            # Show log
            self.log_area.grid(row=1, column=0, sticky="nsew")
            self.log_frame.grid_rowconfigure(1, weight=1)
            self.main_frame.grid_rowconfigure(2, weight=1) # Expand log frame row in main frame
            self.toggle_log_button.config(text="隱藏日誌")
            self.log_visible = True
            self.root.geometry("575x540") # Removed to let notebook expand

    def test_overlay(self, name):
        instance = self.instances[name]
        if instance.get("overlay") is None:
            # 嘗試使用設定的標題，若無則使用模擬器名稱
            target_title = instance["ui"]["overlay_target_title_entry"].get()
            if not target_title:
                target_title = name
            
            # 讀取進階設定
            try:
                offset_x = int(instance["ui"]["overlay_offset_x_entry"].get())
            except: offset_x = -200
            
            try:
                offset_y = int(instance["ui"]["overlay_offset_y_entry"].get())
            except: offset_y = 60

            try:
                font_size = int(instance["ui"]["overlay_font_size_entry"].get())
            except: font_size = 16

            try:
                alpha = float(instance["ui"]["overlay_alpha_entry"].get())
            except: alpha = 0.7

            instance["overlay"] = Overlay(
                target_title=target_title, 
                width=180, 
                font_size=font_size,
                alpha=alpha,
                offset_x=offset_x,
                offset_y=offset_y
            )
        
        # 切換 Overlay 掃描狀態
        if instance.get("is_overlay_scanning", False):
            instance["is_overlay_scanning"] = False
            instance["ui"]["monster_detection_button"].config(text="名單 Overlay")
            instance["overlay"].hide() # 停止時隱藏
        else:
            instance["is_overlay_scanning"] = True
            instance["ui"]["monster_detection_button"].config(text="停止 Overlay")
            
            # 獲取 Overlay 專用目標列表 (在主執行緒讀取 UI)
            raw_targets = instance["ui"]["overlay_target_entry"].get("1.0", tk.END).strip()
            target_list = [t.strip() for t in raw_targets.replace("\n", ",").split(',') if t.strip()]

            # 啟動執行緒進行持續檢查
            threading.Thread(target=self._overlay_check_loop, args=(name, target_list), daemon=True).start()

    def _overlay_check_loop(self, name, target_list):
        instance = self.instances[name]
        overlay = instance["overlay"]
        ui = instance["ui"]
        
        while instance.get("is_overlay_scanning", False):
            try:
                api = instance.get("script_api")
                if not api:
                    overlay.update_text(f"未連接\n模擬器: {name}", font_color=(128, 128, 128))
                    time.sleep(1)
                    continue

                if not target_list:
                    overlay.update_text(f"未設定監控目標\n模擬器: {name}", font_color=(255, 255, 0))
                    time.sleep(1)
                    continue

                # 呼叫 201 指令獲取玩家自身資訊 (用於計算方位+距離)
                player_info_str = api.get_info(201)
                px, py = None, None
                if player_info_str:
                    try:
                        p_json = json.loads(player_info_str)
                        if p_json.get("status") == "success":
                            p_data = p_json.get("data", {})
                            if isinstance(p_data, dict) and "x" in p_data:
                                px = p_data.get("x")
                                py = p_data.get("y")
                            else:
                                px = p_json.get("x")
                                py = p_json.get("y")
                    except:
                        pass

                # 呼叫 203 指令獲取周圍物件
                result_str = api.get_info(203)
                if not result_str:
                    time.sleep(0.5)
                    continue

                result = json.loads(result_str)
                data = result.get("data", [])
                
                # 🚀 改用距離排序：儲存 (顯示文字, 距離) 配對
                found_targets_with_dist = []
                for obj in data:
                    if obj.get("name") in target_list:
                        ox, oy = obj.get("x"), obj.get("y")
                        
                        # 計算歐幾里德距離
                        if px is not None and py is not None and ox is not None and oy is not None:
                            dist = ((ox - px) ** 2 + (oy - py) ** 2) ** 0.5
                        else:
                            dist = 9999  # 無座標時放最遠
                        
                        arrow = self._get_direction_arrow(px, py, ox, oy)
                        if not arrow and (px is None or py is None):
                            arrow = "(?)"
                        
                        display_name = f"{obj.get('name')} {arrow}"
                        found_targets_with_dist.append((display_name, dist))
                
                if found_targets_with_dist:
                    total_count = len(found_targets_with_dist)

                    # 先算每個名稱的最近距離 (去重用最近那一隻)
                    nearest_dist_map = {}
                    for name, dist in found_targets_with_dist:
                        if name not in nearest_dist_map or dist < nearest_dist_map[name]:
                            nearest_dist_map[name] = dist

                    # 距離最近優先排序後取前 N 個 (從設定讀取)
                    try:
                        max_rows = int(ui["overlay_max_rows_entry"].get())
                    except:
                        max_rows = 7

                    sorted_names = sorted(
                        nearest_dist_map.keys(),
                        key=lambda n: nearest_dist_map[n]
                    )[:max_rows]

                    # 組顯示文字：名稱 + 距離 (取整數或一位小數)
                    lines = []
                    for name in sorted_names:
                        d = nearest_dist_map[name]
                        if d >= 9990:          # 你原本沒座標時用 9999 當假距離
                            lines.append(f"{name}")
                        else:
                            lines.append(f"{name} ({int(d)}格)")   # 或 f"{d:.1f}格"

                    display_text = "\n".join(lines)

                    if total_count > max_rows:
                        display_text += f"\n...等共 {total_count} 隻"

                    # 寬度計算
                    try:
                        fixed_width = int(ui["overlay_width_entry"].get())
                    except: fixed_width = 0

                    if fixed_width > 0:
                        target_width = fixed_width
                    else:
                        # 自動寬度
                        line_list = display_text.split("\n")
                        max_chars = max(len(line) for line in line_list)
                        target_width = max(140, min(420, max_chars * 11 + 40))

                    if abs(target_width - overlay.width) > 1:
                        overlay.set_width(target_width)
                        # print(f"寬度: {target_width}px")

                    # 讀取即時設定
                    try:
                        font_size = int(ui["overlay_font_size_entry"].get())
                    except: font_size = 16
                    
                    try:
                        alpha = float(ui["overlay_alpha_entry"].get())
                    except: alpha = 0.7

                    overlay.update_text(display_text, font_color=(255, 255, 0), alpha=alpha, font_size=font_size)
                else:
                    overlay.hide()


            except Exception as e:
                print(f"Overlay check loop error: {e}")
            
            time.sleep(0.5) # 掃描間隔 0.5 秒
        
        # 迴圈結束後確保隱藏
        overlay.hide()

    def _get_direction_arrow(self, px, py, tx, ty):
        if px is None or py is None or tx is None or ty is None:
            return ""
        
        import math
        dx = tx - px
        dy = ty - py
        
        angle = math.degrees(math.atan2(dy, dx))
        if angle < 0:
            angle += 360
        
        if abs(dx) < 1 and abs(dy) < 1:
            return "⏺"
        
        if angle >= 346.7 or angle < 13.3:
            return "↗"
        elif 13.3 <= angle < 58.3:
            return "→"
        elif 58.3 <= angle < 121.7:
            return "↘"
        elif 121.7 <= angle < 166.7:
            return "↓"
        elif 166.7 <= angle < 193.3:
            return "↙"
        elif 193.3 <= angle < 238.3:
            return "←"
        elif 238.3 <= angle < 301.7:
            return "↖"
        else:
            return "↑"

    def create_emulator_tab(self, emu_config):
        name = emu_config.get("name", f"模擬器-{len(self.instances) + 1}")
        
        # 主分頁框架
        tab_frame = ttk.Frame(self.notebook, padding="2")
        self.notebook.add(tab_frame, text=name)

        self.instances[name] = {
            "config": emu_config, "session": None, "is_monitoring": False,
            "monitor_thread": None, "script_api": None, "ui": {},
            "is_seq_moving": False, "seq_move_thread": None,
            "is_patrolling": False, "patrol_thread": None,
            "is_barrier_running": False, "barrier_thread": None,
            "is_monster_detecting": False, "monster_detect_thread": None,
            "last_notification_time": 0,
            "last_notified_target": None,
            "is_timed_targeting": False, 
            "timed_target_thread": None,
            "is_timed_skilling": False, 
            "timed_skill_thread": None,
            "is_auto_barrier_running": False,
            "auto_barrier_thread": None,
            "is_general_afk_running": False,
            "general_afk_buff_thread": None,
            "general_afk_attack_thread": None,
            "buff_last_cast": {},
            "attack_last_cast": {},
            "overlay": None,
            "is_follow_attack_running": False,
            "follow_attack_thread": None,
            "follow_attack_target_id": 0,
            "follow_attack_target_name": "",
            "last_attack_target_id": 0,
            "last_attack_time": 0,
        }
        ui = self.instances[name]["ui"]

        # --- Define UI Variables ---
        ui["monitor_target_var"] = tk.BooleanVar()
        ui["monitor_pos_var"] = tk.BooleanVar()
        ui["monitor_target_teleport_var"] = tk.BooleanVar()
        ui["telegram_notify_var"] = tk.BooleanVar()
        ui["use_forgotten_island_scroll_var"] = tk.BooleanVar()
        ui["auto_attack_pickup_var"] = tk.BooleanVar()
        ui["specify_target_priority_var"] = tk.BooleanVar()

        # Vars for Specify Target
        ui["specify_target_selected_group_name_var"] = tk.StringVar(value="目標組 1")
        ui["specify_target_selected_group_index"] = tk.IntVar(value=0) # 0-indexed
        ui["specify_target_groups"] = [{"name": f"目標組 {i+1}", "targets": ""} for i in range(5)]

        # === 創建子分頁結構 ===
        sub_notebook = ttk.Notebook(tab_frame)
        sub_notebook.pack(expand=True, fill=tk.BOTH)

        # ========== 子分頁 1: 啟用連線 ==========
        connection_tab = ttk.Frame(sub_notebook, padding="5")
        sub_notebook.add(connection_tab, text="啟用連線")
        connection_tab.grid_columnconfigure(0, weight=1)
        connection_tab.grid_columnconfigure(1, weight=1)

        # 主要控制區塊
        connection_frame = ttk.LabelFrame(connection_tab, text="主要控制", padding="5")
        connection_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2), pady=(0, 0))
        
        ttk.Label(connection_frame, text="ADB 路徑:").pack(anchor='w')
        ui["adb_path_entry"] = ttk.Entry(connection_frame)
        ui["adb_path_entry"].pack(pady=(0, 2), fill=tk.X)
        
        ttk.Label(connection_frame, text="端口號:").pack(anchor='w')
        ui["port_entry"] = ttk.Entry(connection_frame)
        ui["port_entry"].pack(pady=(0, 2), fill=tk.X)
        
        ui["connect_button"] = ttk.Button(connection_frame, text="連接", command=lambda n=name: self.connect_thread(n), style='Taller.TButton')
        ui["connect_button"].pack(pady=2, fill=tk.X)

        ui["seq_move_manage_button"] = ttk.Button(connection_frame, text="管理移動路線", command=lambda n=name: self.open_seq_move_dialog(n), style='Taller.TButton')
        ui["seq_move_manage_button"].pack(fill=tk.X, pady=(5, 0))

        ui["advanced_params_button"] = ttk.Button(connection_frame, text="編輯進階參數", command=lambda n=name: self.open_advanced_params_dialog(n), style='Taller.TButton')
        ui["advanced_params_button"].pack(fill=tk.X, pady=(5, 0))

        # Frida 設定區塊
        frida_setup_frame = ttk.LabelFrame(connection_tab, text="Frida 伺服器設定", padding="5")
        frida_setup_frame.grid(row=0, column=1, sticky="nsew", padx=(2, 0), pady=(0, 0))
        frida_setup_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(frida_setup_frame, text="裝置名稱:").grid(row=0, column=0, sticky='w', padx=(0, 5))
        ui["device_serial_entry"] = ttk.Entry(frida_setup_frame, width=12)
        ui["device_serial_entry"].grid(row=0, column=1, sticky='ew', pady=(0, 2))
        
        ttk.Label(frida_setup_frame, text="轉發 Port:").grid(row=1, column=0, sticky='w', padx=(0, 5))
        ui["forward_port_entry"] = ttk.Entry(frida_setup_frame, width=12)
        ui["forward_port_entry"].grid(row=1, column=1, sticky='ew', pady=(0, 2))
        
        ui["start_frida_button"] = ttk.Button(frida_setup_frame, text="啟動 Frida 與轉發", command=lambda n=name: self.start_frida_setup_thread(n), style='Taller.TButton')
        ui["start_frida_button"].grid(row=2, column=0, columnspan=2, sticky='ew', pady=(5, 2))
        
        ui["install_frida_button"] = ttk.Button(frida_setup_frame, text="安裝 Frida", command=lambda n=name: self.install_frida_thread(n), style='Taller.TButton')
        ui["install_frida_button"].grid(row=3, column=0, sticky='ew', padx=(0, 2), pady=(0, 0))
        
        ui["uninstall_frida_button"] = ttk.Button(frida_setup_frame, text="移除 Frida", command=lambda n=name: self.uninstall_frida_thread(n), style='Taller.TButton')
        ui["uninstall_frida_button"].grid(row=3, column=1, sticky='ew', padx=(2, 0), pady=(0, 0))

        # 分隔線
        ttk.Separator(frida_setup_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky='ew', pady=(8, 5))
        
        # 環境就緒檢查 (整合在 Frida 設定區塊內)
        ttk.Label(frida_setup_frame, text="環境狀態:", font=('', 9, 'bold')).grid(row=5, column=0, columnspan=2, sticky='w', padx=5, pady=(0, 2))
        
        # ADB 連線狀態
        ui["adb_status_label"] = ttk.Label(frida_setup_frame, text="● ADB 連線", foreground="gray")
        ui["adb_status_label"].grid(row=6, column=0, columnspan=2, sticky="w", padx=5, pady=1)
        
        # 端口轉發狀態
        ui["forward_status_label"] = ttk.Label(frida_setup_frame, text="● 端口轉發", foreground="gray")
        ui["forward_status_label"].grid(row=7, column=0, columnspan=2, sticky="w", padx=5, pady=1)
        
        # Frida Server 狀態
        ui["frida_status_label"] = ttk.Label(frida_setup_frame, text="● Frida Server", foreground="gray")
        ui["frida_status_label"].grid(row=8, column=0, columnspan=2, sticky="w", padx=5, pady=1)
        
        # 檢查按鈕
        ui["env_check_button"] = ttk.Button(frida_setup_frame, text="檢查環境狀態", 
                                             command=lambda n=name: self.check_environment_status(n),
                                             style='Taller.TButton')
        ui["env_check_button"].grid(row=9, column=0, columnspan=2, sticky='ew', pady=(5, 0))

        # ========== 子分頁 2: 測試 ==========
        test_tab = ttk.Frame(sub_notebook, padding="5")
        sub_notebook.add(test_tab, text="測試區")
        test_tab.grid_columnconfigure(0, weight=1)
        test_tab.grid_columnconfigure(1, weight=1)
        test_tab.grid_rowconfigure(0, weight=1)
        test_tab.grid_rowconfigure(1, weight=1)

        # === 左上區塊：座標移動 ===
        coord_move_frame = ttk.LabelFrame(test_tab, text="座標移動", padding="5")
        coord_move_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2), pady=(0, 2))
        
        coord_frame = ttk.Frame(coord_move_frame)
        coord_frame.pack(fill=tk.X, pady=2)
        ttk.Label(coord_frame, text="X:").pack(side=tk.LEFT)
        ui["x_entry"] = ttk.Entry(coord_frame, width=8)
        ui["x_entry"].pack(side=tk.LEFT, padx=(5, 10))
        ttk.Label(coord_frame, text="Y:").pack(side=tk.LEFT)
        ui["y_entry"] = ttk.Entry(coord_frame, width=8)
        ui["y_entry"].pack(side=tk.LEFT, padx=(5, 0))
        
        ui["moveto_button"] = ttk.Button(coord_move_frame, text="移動到座標", command=lambda n=name: self.run_moveto_thread(n), style='Taller.TButton')
        ui["moveto_button"].pack(fill=tk.X, pady=(5, 0))

        # === 右上區塊：回村與物品 ===
        village_item_frame = ttk.LabelFrame(test_tab, text="回村與物品", padding="5")
        village_item_frame.grid(row=0, column=1, sticky="nsew", padx=(2, 0), pady=(0, 2))
        
        back_village_frame = ttk.Frame(village_item_frame)
        back_village_frame.pack(fill=tk.X, pady=(0, 5))
        ui["back_button"] = ttk.Button(back_village_frame, text="回村", command=lambda n=name: self.back_to_village_thread(n), style='Taller.TButton')
        ui["back_button"].pack(fill=tk.X, pady=(0, 2))
        ttk.Checkbutton(back_village_frame, text="使用遺忘之島卷軸", variable=ui["use_forgotten_island_scroll_var"]).pack(anchor='w')

        item_name_frame = ttk.Frame(village_item_frame)
        item_name_frame.pack(fill=tk.X)
        ttk.Label(item_name_frame, text="物品名稱:").pack(side=tk.LEFT)
        ui["item_name_entry"] = ttk.Entry(item_name_frame)
        ui["item_name_entry"].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0), pady=(0, 5))
        
        ui["use_item_button"] = ttk.Button(village_item_frame, text="使用物品(即時)", command=lambda n=name: self.use_item_thread(n), style='Taller.TButton')
        ui["use_item_button"].pack(fill=tk.X)

        # === 左下區塊：AUTO 控制 ===
        auto_control_frame = ttk.LabelFrame(test_tab, text="AUTO 控制", padding="5")
        auto_control_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 2), pady=(2, 0))
        
        ui["start_auto_button"] = ttk.Button(auto_control_frame, text="啟動 AUTO", command=lambda n=name: self.start_auto_thread(n, True), style='Taller.TButton')
        ui["start_auto_button"].pack(fill=tk.X, pady=(0, 5))
        
        ui["stop_auto_button"] = ttk.Button(auto_control_frame, text="關閉 AUTO", command=lambda n=name: self.start_auto_thread(n, False), style='Taller.TButton')
        ui["stop_auto_button"].pack(fill=tk.X)

        # === 右下區塊：指令執行 ===
        execute_frame = ttk.LabelFrame(test_tab, text="指令執行", padding="5")
        execute_frame.grid(row=1, column=1, sticky="nsew", padx=(2, 0), pady=(2, 0))
        execute_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(execute_frame, text="指令:").grid(row=0, column=0, sticky="w", pady=(0, 2))
        ui["input_entry"] = ttk.Entry(execute_frame, width=5)
        ui["input_entry"].grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=(0, 2))
        
        ttk.Label(execute_frame, text="保留欄位:").grid(row=1, column=0, sticky="w", pady=(0, 5))
        ui["keep_fields_entry"] = ttk.Entry(execute_frame, width=5)
        ui["keep_fields_entry"].grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=(0, 5))
        
        button_frame = ttk.Frame(execute_frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        ui["run_button"] = ttk.Button(button_frame, text="執行", command=lambda n=name: self.run_script_thread(n), style='Taller.TButton')
        ui["run_button"].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ui["show_params_button"] = ttk.Button(button_frame, text="參數說明", command=lambda n=name: self.show_command_params_info(n), style='Taller.TButton')
        ui["show_params_button"].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        button_frame2 = ttk.Frame(execute_frame)
        button_frame2.grid(row=3, column=0, columnspan=2, sticky="ew")
        ui["get_objects_button"] = ttk.Button(button_frame2, text="周圍物件", command=lambda n=name: self.run_quick_command_thread(n, 203, "list_objects"), style='Taller.TButton')
        ui["get_objects_button"].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ui["list_players_button"] = ttk.Button(button_frame2, text="周圍玩家", command=lambda n=name: self.list_nearby_players_thread(n), style='Taller.TButton')
        ui["list_players_button"].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # ========== 子分頁 3: 功能區 ==========
        features_tab = ttk.Frame(sub_notebook, padding="5")
        sub_notebook.add(features_tab, text="功能區")
        features_tab.grid_columnconfigure(0, weight=1, uniform="features_cols")
        features_tab.grid_columnconfigure(1, weight=1, uniform="features_cols")

        # 左側功能區
        left_features_frame = ttk.Frame(features_tab)
        left_features_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 3))

        # Overlay 設定
        overlay_settings_frame = ttk.LabelFrame(left_features_frame, text="Overlay 設定", padding="5")
        overlay_settings_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 模擬器標題（標籤和輸入框在同一行）
        title_frame = ttk.Frame(overlay_settings_frame)
        title_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(title_frame, text="模擬器標題:").pack(side=tk.LEFT)
        ui["overlay_target_title_entry"] = ttk.Entry(title_frame)
        ui["overlay_target_title_entry"].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # 按鈕列 (編輯目標 + 進階設定)
        overlay_btn_frame = ttk.Frame(overlay_settings_frame)
        overlay_btn_frame.pack(fill=tk.X, pady=(0, 5))

        ui["edit_overlay_targets_button"] = ttk.Button(overlay_btn_frame, text="編輯目標", command=lambda n=name: self.open_overlay_target_list_dialog(n), style='Taller.TButton')
        ui["edit_overlay_targets_button"].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        ui["overlay_advanced_settings_button"] = ttk.Button(overlay_btn_frame, text="進階設定", command=lambda n=name: self.open_overlay_advanced_settings_dialog(n), style='Taller.TButton')
        ui["overlay_advanced_settings_button"].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        ui["monster_detection_button"] = ttk.Button(overlay_settings_frame, text="名單 Overlay", command=lambda n=name: self.test_overlay(n), style='Taller.TButton')
        ui["monster_detection_button"].pack(fill=tk.X)

        # 自動功能（2 列布局）
        auto_features_frame = ttk.LabelFrame(left_features_frame, text="自動功能", padding="5")
        auto_features_frame.pack(fill=tk.X, pady=(0, 5))
        auto_features_frame.grid_columnconfigure(0, weight=1)
        auto_features_frame.grid_columnconfigure(1, weight=1)

        # 第一行：自動巡邏設定 | 自動聚怪
        ui["patrol_control_button"] = ttk.Button(auto_features_frame, text="自動巡邏設定", command=lambda n=name: self.open_patrol_dialog(n), style='Taller.TButton')
        ui["patrol_control_button"].grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=(0, 2))

        ui["test_features_button"] = ttk.Button(auto_features_frame, text="自動聚怪", command=lambda n=name: self.open_test_features_dialog(n), style='Taller.TButton')
        ui["test_features_button"].grid(row=0, column=1, sticky="ew", padx=(2, 0), pady=(0, 2))

        # 第二行：循序移動控制 | 自動聖結界
        ui["seq_move_control_button"] = ttk.Button(auto_features_frame, text="循序移動控制", command=lambda n=name: self.open_seq_move_control_dialog(n), style='Taller.TButton')
        ui["seq_move_control_button"].grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=(0, 2))

        ui["auto_barrier_button"] = ttk.Button(auto_features_frame, text="自動聖結界", command=lambda n=name: self.open_auto_barrier_dialog(n), style='Taller.TButton')
        ui["auto_barrier_button"].grid(row=1, column=1, sticky="ew", padx=(2, 0), pady=(0, 2))

        # 第三行：一般掛機 | 進階功能
        ui["general_afk_button"] = ttk.Button(auto_features_frame, text="一般掛機", command=lambda n=name: self.open_general_afk_dialog(n), style='Taller.TButton')
        ui["general_afk_button"].grid(row=2, column=0, sticky="ew", padx=(0, 2), pady=(0, 2))

        ui["advanced_features_button"] = ttk.Button(auto_features_frame, text="進階功能", command=lambda n=name: self.open_advanced_features_dialog(n), style='Taller.TButton')
        ui["advanced_features_button"].grid(row=2, column=1, sticky="ew", padx=(2, 0), pady=(0, 2))

        # 第四行：跟隨攻擊
        ui["follow_attack_button"] = ttk.Button(auto_features_frame, text="跟隨攻擊", command=lambda n=name: self.open_follow_attack_dialog(n), style='Taller.TButton')
        ui["follow_attack_button"].grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        
        # 一般掛機狀態標籤（跨兩列）
        ui["general_afk_main_status_label"] = ttk.Label(auto_features_frame, text="未啟動", foreground="gray", anchor="center")
        ui["general_afk_main_status_label"].grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 0))

        # 右側監控區
        right_features_frame = ttk.Frame(features_tab)
        right_features_frame.grid(row=0, column=1, sticky="nsew", padx=(3, 0))

        monitor_frame = ttk.LabelFrame(right_features_frame, text="自動監控", padding="5")
        monitor_frame.pack(fill=tk.X)
        monitor_frame.grid_columnconfigure(1, weight=1)

        # 目標監控
        ttk.Checkbutton(monitor_frame, text="監控目標", variable=ui["monitor_target_var"]).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(monitor_frame, text="遇到回村", variable=ui["monitor_target_teleport_var"]).grid(row=0, column=1, sticky="w")
        
        ui["edit_targets_button"] = ttk.Button(monitor_frame, text="編輯監控目標", command=lambda n=name: self.open_target_list_dialog(n), style='Taller.TButton')
        ui["edit_targets_button"].grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
        
        ui["target_entry"] = scrolledtext.ScrolledText(monitor_frame, height=3, width=20) 
        ui["target_interval_entry"] = ttk.Entry(monitor_frame, width=10)
        
        # Overlay 專用目標列表（隱藏）
        ui["overlay_target_entry"] = scrolledtext.ScrolledText(monitor_frame, height=3, width=20)

        # 座標監控
        ttk.Checkbutton(monitor_frame, text="監控座標", variable=ui["monitor_pos_var"]).grid(row=2, column=0, sticky="w", pady=(5, 0))
        ui["coord_monitor_button"] = ttk.Button(monitor_frame, text="座標設定", command=lambda n=name: self.open_coord_monitor_dialog(n), style='Taller.TButton')
        ui["coord_monitor_button"].grid(row=2, column=1, sticky="ew", pady=(5,0))

        ui["monitor_x_entry"] = ttk.Entry(monitor_frame)
        ui["monitor_y_entry"] = ttk.Entry(monitor_frame)
        ui["monitor_range_entry"] = ttk.Entry(monitor_frame)
        ui["pos_interval_entry"] = ttk.Entry(monitor_frame)

        # 通知設定
        ttk.Checkbutton(monitor_frame, text="TG 通知", variable=ui["telegram_notify_var"]).grid(row=3, column=0, sticky="w", pady=(5, 0))
        ui["telegram_chat_id_entry"] = ttk.Entry(monitor_frame, width=10)
        ui["telegram_chat_id_entry"].grid(row=3, column=1, sticky="ew", pady=(5,0))

        # 開始監控按鈕
        ui["monitor_button"] = ttk.Button(monitor_frame, text="開始監控", command=lambda n=name: self.toggle_monitoring(n), style='Taller.TButton')
        ui["monitor_button"].grid(row=5, column=0, columnspan=2, pady=(10, 0), sticky="ew")

        # 自動魔法屏障
        barrier_frame = ttk.LabelFrame(right_features_frame, text="自動魔法屏障", padding="5")
        barrier_frame.pack(fill=tk.X, pady=(5, 0))
        barrier_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(barrier_frame, text="間隔(秒):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ui["barrier_interval_entry"] = ttk.Entry(barrier_frame, width=10)
        ui["barrier_interval_entry"].grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        ui["barrier_toggle_button"] = ttk.Button(barrier_frame, text="開始施放", command=lambda n=name: self.toggle_auto_barrier(n), style='Taller.TButton')
        ui["barrier_toggle_button"].grid(row=1, column=0, columnspan=2, pady=5, sticky="ew")

        # --- 隱藏的進階參數 (不顯示在 UI 中，但需要存在以供其他功能使用) ---
        hidden_frame = ttk.Frame(tab_frame)  # 不 pack，所以不會顯示
        
        ui["c0391_class_name_entry"] = ttk.Entry(hidden_frame)
        ui["socket_utils_method_entry"] = ttk.Entry(hidden_frame)
        ui["moveto_classname_entry"] = ttk.Entry(hidden_frame)
        ui["use_item_method_name_entry"] = ttk.Entry(hidden_frame)
        ui["auto_method_entry"] = ttk.Entry(hidden_frame)
        ui["skill_use_method_name_entry"] = ttk.Entry(hidden_frame)
        ui["target_method_name_entry"] = ttk.Entry(hidden_frame)
        ui["attack_pickup_method_name_entry"] = ttk.Entry(hidden_frame)
        ui["skill_id_entry"] = ttk.Entry(hidden_frame)
        ui["select_skill_button"] = ttk.Button(hidden_frame)
        ui["use_skill_button"] = ttk.Button(hidden_frame)
        ui["timed_skill_button"] = ttk.Button(hidden_frame)
        ui["timed_skill_interval_entry"] = ttk.Entry(hidden_frame)

        ui["specify_target_group_combobox"] = ttk.Combobox(hidden_frame)
        ui["edit_specify_targets_button"] = ttk.Button(hidden_frame)
        ui["specify_target_button"] = ttk.Button(hidden_frame)
        ui["timed_target_button"] = ttk.Button(hidden_frame)
        ui["timed_target_interval_entry"] = ttk.Entry(hidden_frame)
        ui["timed_target_interval_entry"] = ttk.Entry(hidden_frame)
        ui["specify_target_current_targets_text"] = scrolledtext.ScrolledText(hidden_frame)

        # Overlay Advanced Settings (Hidden)
        ui["overlay_offset_x_entry"] = ttk.Entry(hidden_frame)
        ui["overlay_offset_y_entry"] = ttk.Entry(hidden_frame)
        ui["overlay_font_size_entry"] = ttk.Entry(hidden_frame)
        ui["overlay_alpha_entry"] = ttk.Entry(hidden_frame)
        ui["overlay_max_rows_entry"] = ttk.Entry(hidden_frame)
        ui["overlay_width_entry"] = ttk.Entry(hidden_frame)

        ui["coord_presets_entries"] = []
        for i in range(10):
            name_entry = ttk.Entry(hidden_frame)
            x_entry = ttk.Entry(hidden_frame)
            y_entry = ttk.Entry(hidden_frame)
            ui["coord_presets_entries"].append({"name": name_entry, "x": x_entry, "y": y_entry})
        
        ui["seq_move_presets"] = []

        ui["specify_target_current_targets_text"].config(state='disabled')

        self.load_config_into_ui(name)
        self.set_action_buttons_state(name, 'disabled')
        ui["barrier_toggle_button"].config(state='disabled')

    def load_and_create_tabs(self):
        if not os.path.exists(CONFIG_FILE):
            self.log_message(f"[警告] 找不到設定檔 {CONFIG_FILE}。")
            self.button_padding_entry.insert(0, "2")
            self.log_height_entry.insert(0, "8")
            self.apply_custom_styles()
            messagebox.showwarning("無設定檔", f'找不到 {CONFIG_FILE}。\n請至少設定一個模擬器並儲存。')
            return
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            config_data = self.config

            global_settings = config_data.get("global_settings", {})
            button_padding = global_settings.get("button_padding", "2")
            self.button_padding_entry.insert(0, button_padding)
            
            log_height = global_settings.get("log_height", "8")
            self.log_height_entry.insert(0, log_height)
            
            self.apply_custom_styles()

            for emu_config in config_data.get("emulators", []):
                if emu_config.get("enabled", True):
                    self.create_emulator_tab(emu_config)
            self.log_message(f"[提示] 成功從 {CONFIG_FILE} 載入 {len(self.instances)} 個模擬器設定。")

            self.create_independent_control_tab()
        except (json.JSONDecodeError, IOError) as e:
            self.log_message(f"[錯誤] 載入設定檔失敗: {e}")
            messagebox.showerror("設定檔錯誤", f'無法讀取或解析 {CONFIG_FILE}:\n{e}')

    def load_config_into_ui(self, name):
        emu_config = self.instances[name]["config"]
        global_config = self.config
        ui = self.instances[name]["ui"]
        
        def set_val(w, k, d=""): w.delete(0, tk.END); w.insert(0, emu_config.get(k, d))
        def set_text(w, k, d=""): w.delete("1.0", tk.END); w.insert("1.0", emu_config.get(k, d))
        def set_bool(v, k, d=False): v.set(emu_config.get(k, d))
        def set_global_val(w, k, d=""): w.delete(0, tk.END); w.insert(0, global_config.get(k, d))

        set_val(ui["adb_path_entry"], "adb_path", "C:\\LDPlayer\\LDPlayer9\\adb.exe")
        set_val(ui["port_entry"], "port", "27043")
        set_val(ui["device_serial_entry"], "device_serial", "emulator-5554")
        set_val(ui["forward_port_entry"], "forward_port", "27043")
        set_val(ui["input_entry"], "input_code", "201")
        set_val(ui["keep_fields_entry"], "keep_fields", "")
        set_val(ui["item_name_entry"], "use_item_name", "")

        set_global_val(ui["moveto_classname_entry"], "moveto_classname", "䄼")
        set_global_val(ui["use_item_method_name_entry"], "use_item_method_name", "䇪")
        set_global_val(ui["auto_method_entry"], "auto_method", "")
        set_global_val(ui["skill_use_method_name_entry"], "skill_use_method_name", "")
        set_global_val(ui["target_method_name_entry"], "target_method_name", "")
        set_global_val(ui["attack_pickup_method_name_entry"], "attack_pickup_method_name", "")
        set_global_val(ui["c0391_class_name_entry"], "c0391_class_name", "ቌ.ᣇ.ᶬ.ಞ.㚽.Ố")
        set_global_val(ui["socket_utils_method_entry"], "socket_utils_method", "ᶬ")
        set_val(ui["overlay_target_title_entry"], "overlay_target_title", "天堂M-3-LD9")
        set_val(ui["overlay_offset_x_entry"], "overlay_offset_x", "-200")
        set_val(ui["overlay_offset_y_entry"], "overlay_offset_y", "60")
        set_val(ui["overlay_font_size_entry"], "overlay_font_size", "16")
        set_val(ui["overlay_alpha_entry"], "overlay_alpha", "0.7")
        set_val(ui["overlay_max_rows_entry"], "overlay_max_rows", "7")
        set_val(ui["overlay_width_entry"], "overlay_width", "0")
        
        set_bool(ui["monitor_target_var"], "monitor_target_on", False)
        set_bool(ui["monitor_target_teleport_var"], "monitor_target_teleport_on", True)
        set_text(ui["target_entry"], "monitor_targets", "")
        set_text(ui["overlay_target_entry"], "overlay_targets", "")
        set_val(ui["target_interval_entry"], "target_interval", "0.5")
        set_bool(ui["monitor_pos_var"], "monitor_pos_on", False)
        set_val(ui["monitor_x_entry"], "monitor_x", "32768")
        set_val(ui["monitor_y_entry"], "monitor_y", "32768")
        set_val(ui["monitor_range_entry"], "monitor_range", "100")
        set_val(ui["pos_interval_entry"], "pos_interval", "3")
        set_val(ui["barrier_interval_entry"], "barrier_interval", "5")

        set_bool(ui["telegram_notify_var"], "telegram_notify_on", True)
        set_bool(ui["use_forgotten_island_scroll_var"], "use_forgotten_island_scroll", False)
        set_bool(ui["auto_attack_pickup_var"], "auto_attack_pickup_on", False)
        if "specify_target_priority_var" not in ui:
            ui["specify_target_priority_var"] = tk.BooleanVar()
        set_bool(ui["specify_target_priority_var"], "specify_target_priority_on", False)
        set_val(ui["telegram_chat_id_entry"], "telegram_chat_id", "")
        set_val(ui["timed_target_interval_entry"], "timed_target_interval", "1")
        set_val(ui["timed_skill_interval_entry"], "timed_skill_interval", "1")

        coord_presets = emu_config.get("coord_presets", [])
        for i in range(10):
            ui["coord_presets_entries"][i]["name"].delete(0, tk.END)
            ui["coord_presets_entries"][i]["x"].delete(0, tk.END)
            ui["coord_presets_entries"][i]["y"].delete(0, tk.END)
            if i < len(coord_presets):
                preset = coord_presets[i]
                ui["coord_presets_entries"][i]["name"].insert(0, preset.get("name", f"座標 {i+1}"))
                ui["coord_presets_entries"][i]["x"].insert(0, preset.get("x", ""))
                ui["coord_presets_entries"][i]["y"].insert(0, preset.get("y", ""))
            else:
                ui["coord_presets_entries"][i]["name"].insert(0, f"座標 {i+1}")

        # Load specify target groups
        loaded_groups = emu_config.get("specify_target_groups", [])
        if loaded_groups:
            for i, group_data in enumerate(loaded_groups):
                if i < 5:
                    ui["specify_target_groups"][i]["name"] = group_data.get("name", f"目標組 {i+1}")
                    ui["specify_target_groups"][i]["targets"] = group_data.get("targets", "")
        
        selected_group_index = emu_config.get("specify_target_selected_group_index", 0)
        if 0 <= selected_group_index < 5:
            ui["specify_target_selected_group_index"].set(selected_group_index)
            ui["specify_target_selected_group_name_var"].set(ui["specify_target_groups"][selected_group_index]["name"])
            
            # Initialize combobox values and selection
            new_combobox_values = [group["name"] for group in ui["specify_target_groups"]]
            ui["specify_target_group_combobox"]['values'] = new_combobox_values
            ui["specify_target_group_combobox"].set(ui["specify_target_groups"][selected_group_index]["name"])

            ui["specify_target_current_targets_text"].config(state='normal')
            ui["specify_target_current_targets_text"].delete("1.0", tk.END)
            ui["specify_target_current_targets_text"].insert("1.0", ui["specify_target_groups"][selected_group_index]["targets"])
            ui["specify_target_current_targets_text"].config(state='disabled')
        else:
            ui["specify_target_selected_group_index"].set(0)
            ui["specify_target_selected_group_name_var"].set(ui["specify_target_groups"][0]["name"])
            
            # Initialize combobox values and selection for default
            new_combobox_values = [group["name"] for group in ui["specify_target_groups"]]
            ui["specify_target_group_combobox"]['values'] = new_combobox_values
            ui["specify_target_group_combobox"].set(ui["specify_target_groups"][0]["name"])

            ui["specify_target_current_targets_text"].config(state='normal')
            ui["specify_target_current_targets_text"].delete("1.0", tk.END)
            ui["specify_target_current_targets_text"].insert("1.0", ui["specify_target_groups"][0]["targets"])
            ui["specify_target_current_targets_text"].config(state='disabled')


        self.instances[name]["seq_move_threshold"] = emu_config.get("seq_move_threshold", "10")
        self.instances[name]["seq_move_interval"] = emu_config.get("seq_move_interval", "2")

        # Load auto patrol settings
        self.instances[name]["patrol_interval"] = emu_config.get("patrol_interval", "5")
        self.instances[name]["patrol_attacker_threshold"] = emu_config.get("patrol_attacker_threshold", "1")
        self.instances[name]["patrol_range"] = emu_config.get("patrol_range", "30")
        self.instances[name]["patrol_toggle_auto"] = emu_config.get("patrol_toggle_auto", True)
        self.instances[name]["patrol_condition"] = emu_config.get("patrol_condition", "被攻擊者少於")
        self.instances[name]["patrol_move_type"] = emu_config.get("patrol_move_type", "隨機移動")
        self.instances[name]["patrol_selected_route_name"] = emu_config.get("patrol_selected_route_name", "")
        self.instances[name]["patrol_arrival_threshold"] = emu_config.get("patrol_arrival_threshold", "5")
        self.instances[name]["patrol_attack_on_arrival"] = emu_config.get("patrol_attack_on_arrival", False)
        self.instances[name]["patrol_priority_pickup"] = emu_config.get("patrol_priority_pickup", True)
        self.instances[name]["patrol_nearby_range"] = emu_config.get("patrol_nearby_range", "3")
        self.instances[name]["patrol_nearby_threshold"] = emu_config.get("patrol_nearby_threshold", "1")



        # Load sequential move presets
        ui["seq_move_presets"] = emu_config.get("seq_move_presets", [])

        # Load priority targeting (auto-gather) settings into the instance config
        self.instances[name]["config"]["priority_attacker_threshold"] = emu_config.get("priority_attacker_threshold", "3")
        self.instances[name]["config"]["priority_lower_threshold"] = emu_config.get("priority_lower_threshold", "1")
        self.instances[name]["config"]["priority_skill_id"] = emu_config.get("priority_skill_id", "")
        self.instances[name]["config"]["priority_interval"] = emu_config.get("priority_interval", "0.5")
        self.instances[name]["config"]["priority_luring_range"] = emu_config.get("priority_luring_range", "50")
        self.instances[name]["config"]["priority_pickup_list"] = emu_config.get("priority_pickup_list", "")
        self.instances[name]["config"]["priority_monster_blacklist"] = emu_config.get("priority_monster_blacklist", "史萊姆,葛林")
        self.instances[name]["config"]["priority_density_detection"] = emu_config.get("priority_density_detection", False)
        self.instances[name]["config"]["priority_cluster_radius"] = emu_config.get("priority_cluster_radius", "15")

        # Load auto barrier settings
        self.instances[name]["config"]["auto_barrier_targets"] = emu_config.get("auto_barrier_targets", "")
        self.instances[name]["config"]["auto_barrier_interval"] = emu_config.get("auto_barrier_interval", "2")
        self.instances[name]["config"]["auto_barrier_pre_cast_delay"] = emu_config.get("auto_barrier_pre_cast_delay", "0.5")
        self.instances[name]["config"]["auto_barrier_advance_time"] = emu_config.get("auto_barrier_advance_time", "5.0")
        self.instances[name]["config"]["holy_barrier_duration"] = emu_config.get("holy_barrier_duration", "180")
        self.instances[name]["config"]["barrier_cast_cooldown"] = emu_config.get("barrier_cast_cooldown", "60")
        self.instances[name]["config"]["auto_barrier_move_to_cast"] = emu_config.get("auto_barrier_move_to_cast", False)
        self.instances[name]["config"]["auto_barrier_use_cache"] = emu_config.get("auto_barrier_use_cache", True)
        
        if "auto_barrier_enable_clan_filter_var" in ui:
            set_bool(ui["auto_barrier_enable_clan_filter_var"], "auto_barrier_enable_clan_filter", False)
        if "auto_barrier_clan_filter_entry" in ui:
            set_val(ui["auto_barrier_clan_filter_entry"], "auto_barrier_clan_filter_name", "")

    def save_config(self):
        all_configs = {
            "global_settings": {
                "button_padding": self.button_padding_entry.get(),
                "log_height": self.log_height_entry.get(),
                # Monster HP Detection Settings
                "monster_hp_detection_monster_name": getattr(self, "monster_name_entry", tk.Entry()).get(),
                "monster_hp_detection_threshold": getattr(self, "hp_threshold_entry", tk.Entry()).get(),
                "monster_hp_detection_instance": getattr(self, "detection_instance_var", tk.StringVar()).get()
            }
        }

        if self.instances:
            first_instance_ui = next(iter(self.instances.values()))["ui"]
            all_configs["moveto_classname"] = first_instance_ui["moveto_classname_entry"].get()
            all_configs["use_item_method_name"] = first_instance_ui["use_item_method_name_entry"].get()
            all_configs["auto_method"] = first_instance_ui["auto_method_entry"].get()
            all_configs["skill_use_method_name"] = first_instance_ui["skill_use_method_name_entry"].get()
            all_configs["target_method_name"] = first_instance_ui["target_method_name_entry"].get()
            all_configs["attack_pickup_method_name"] = first_instance_ui["attack_pickup_method_name_entry"].get()
            all_configs["c0391_class_name"] = first_instance_ui["c0391_class_name_entry"].get()
            all_configs["socket_utils_method"] = first_instance_ui["socket_utils_method_entry"].get()

        all_configs["emulators"] = []
        
        # First, sync independent control settings back to emulator configs
        for name, instance in self.instances.items():
            if name.startswith("獨立-"):
                # Extract index from name (e.g., "獨立-1" -> 0)
                try:
                    idx = int(name.split("-")[1]) - 1
                    if idx >= 0 and idx < len(list(self.instances.items())):
                        # Find the corresponding emulator instance
                        emulator_instances = [n for n in self.instances.keys() if not n.startswith("獨立-")]
                        if idx < len(emulator_instances):
                            emu_name = emulator_instances[idx]
                            # Sync target groups and settings from independent control to emulator
                            ui_independent = instance["ui"]
                            ui_emulator = self.instances[emu_name]["ui"]
                            ui_emulator["specify_target_groups"] = ui_independent["specify_target_groups"]
                            ui_emulator["specify_target_selected_group_index"].set(ui_independent["specify_target_selected_group_index"].get())
                            ui_emulator["auto_attack_pickup_var"].set(ui_independent["auto_attack_pickup_var"].get())
                            ui_emulator["specify_target_priority_var"].set(ui_independent["specify_target_priority_var"].get())
                            # Sync interval setting to instance config (not UI, as it's stored in config)
                            self.instances[emu_name]["config"]["timed_target_interval"] = ui_independent["timed_target_interval_entry"].get()
                            self.instances[emu_name]["config"]["barrier_interval"] = ui_independent["barrier_interval_entry"].get()
                except (ValueError, IndexError):
                    pass
        
        # Now save all emulator configs (skip independent control instances)
        for name, instance in self.instances.items():
            # Skip independent control instances
            if name.startswith("獨立-"):
                continue
                
            ui = instance["ui"]
            raw_targets = ui["target_entry"].get("1.0", tk.END).strip()
            processed_targets = ",".join([t.strip() for t in raw_targets.replace("\n", ",").split(',') if t.strip()])
            
            # Overlay 目標列表
            raw_overlay_targets = ui["overlay_target_entry"].get("1.0", tk.END).strip()
            processed_overlay_targets = ",".join([t.strip() for t in raw_overlay_targets.replace("\n", ",").split(',') if t.strip()])
            
            emu_conf = {
                "name": name, "enabled": True,
                "adb_path": ui["adb_path_entry"].get(), "port": ui["port_entry"].get(),
                "device_serial": ui["device_serial_entry"].get(), "forward_port": ui["forward_port_entry"].get(),
                "input_code": ui["input_entry"].get(), "keep_fields": ui["keep_fields_entry"].get(),
                "use_item_name": ui["item_name_entry"].get(),
                "monitor_target_on": ui["monitor_target_var"].get(),
                "monitor_target_teleport_on": ui["monitor_target_teleport_var"].get(),
                "monitor_targets": processed_targets,
                "overlay_targets": processed_overlay_targets,
                "target_interval": ui["target_interval_entry"].get(),
                "monitor_pos_on": ui["monitor_pos_var"].get(),
                "monitor_x": ui["monitor_x_entry"].get(), "monitor_y": ui["monitor_y_entry"].get(),
                "monitor_range": ui["monitor_range_entry"].get(), "pos_interval": ui["pos_interval_entry"].get(),
                "barrier_interval": ui["barrier_interval_entry"].get(),
                "telegram_chat_id": ui["telegram_chat_id_entry"].get(),
                "telegram_notify_on": ui["telegram_notify_var"].get(),
                "use_forgotten_island_scroll": ui["use_forgotten_island_scroll_var"].get(),
                "auto_attack_pickup_on": ui["auto_attack_pickup_var"].get(),
                "specify_target_priority_on": ui["specify_target_priority_var"].get(),
                "overlay_target_title": ui["overlay_target_title_entry"].get(),
            }
            # Values from dialogs are saved to instance["config"] to avoid errors from destroyed widgets
            emu_conf["timed_target_interval"] = instance["config"].get("timed_target_interval", "1")
            emu_conf["timed_skill_interval"] = instance["config"].get("timed_skill_interval", "1")
            emu_conf["skill_id"] = instance["config"].get("skill_id", "")

            # Save priority targeting (auto-gather) settings
            emu_conf["priority_attacker_threshold"] = instance["config"].get("priority_attacker_threshold", "3")
            emu_conf["priority_lower_threshold"] = instance["config"].get("priority_lower_threshold", "1")
            emu_conf["priority_skill_id"] = instance["config"].get("priority_skill_id", "")
            emu_conf["priority_interval"] = instance["config"].get("priority_interval", "0.5")
            emu_conf["priority_luring_range"] = instance["config"].get("priority_luring_range", "50")
            emu_conf["priority_pickup_range"] = instance["config"].get("priority_pickup_range", "200")
            emu_conf["priority_pickup_list"] = instance["config"].get("priority_pickup_list", "")
            emu_conf["priority_monster_blacklist"] = instance["config"].get("priority_monster_blacklist", "史萊姆,葛林")
            emu_conf["priority_density_detection"] = instance["config"].get("priority_density_detection", False)
            emu_conf["priority_cluster_radius"] = instance["config"].get("priority_cluster_radius", "15")
            emu_conf["priority_safety_distance"] = instance["config"].get("priority_safety_distance", "2")
            emu_conf["priority_safety_count"] = instance["config"].get("priority_safety_count", "2")
            emu_conf["priority_stuck_teleport"] = instance["config"].get("priority_stuck_teleport", False)
            emu_conf["priority_stuck_time"] = instance["config"].get("priority_stuck_time", "5")
            
            # Save General AFK settings
            emu_conf["general_afk_buff_skills"] = instance["config"].get("general_afk_buff_skills", [])
            emu_conf["general_afk_attack_skills"] = instance["config"].get("general_afk_attack_skills", [])
            emu_conf["general_afk_stop_on_map_change"] = instance["config"].get("general_afk_stop_on_map_change", False)
            
            emu_conf["seq_move_threshold"] = instance.get("seq_move_threshold", "10")
            emu_conf["seq_move_interval"] = instance.get("seq_move_interval", "2")

            # Save auto patrol settings
            emu_conf["patrol_interval"] = instance["config"].get("patrol_interval", "5")
            emu_conf["patrol_attacker_threshold"] = instance["config"].get("patrol_attacker_threshold", "1")
            emu_conf["patrol_range"] = instance["config"].get("patrol_range", "30")
            emu_conf["patrol_toggle_auto"] = instance["config"].get("patrol_toggle_auto", True)
            emu_conf["patrol_condition"] = instance["config"].get("patrol_condition", "被攻擊者少於")
            emu_conf["patrol_move_type"] = instance["config"].get("patrol_move_type", "隨機移動")
            emu_conf["patrol_selected_route_name"] = instance["config"].get("patrol_selected_route_name", "")
            emu_conf["patrol_arrival_threshold"] = instance["config"].get("patrol_arrival_threshold", "5")
            emu_conf["patrol_attack_on_arrival"] = instance["config"].get("patrol_attack_on_arrival", False)
            emu_conf["patrol_priority_pickup"] = instance["config"].get("patrol_priority_pickup", True)
            emu_conf["patrol_nearby_range"] = instance["config"].get("patrol_nearby_range", "3")
            emu_conf["patrol_nearby_threshold"] = instance["config"].get("patrol_nearby_threshold", "1")



            coord_presets_data = []
            for preset_entries in ui["coord_presets_entries"]:
                name_val = preset_entries["name"].get()
                x_val = preset_entries["x"].get()
                y_val = preset_entries["y"].get()
                coord_presets_data.append({"name": name_val, "x": x_val, "y": y_val})
            emu_conf["coord_presets"] = coord_presets_data
            
            emu_conf["specify_target_groups"] = ui["specify_target_groups"]
            emu_conf["specify_target_selected_group_index"] = ui["specify_target_selected_group_index"].get()

            # Save sequential move presets
            emu_conf["seq_move_presets"] = ui["seq_move_presets"]

                        # Save auto barrier settings
            emu_conf["auto_barrier_targets"] = instance["config"].get("auto_barrier_targets", "")

            emu_conf["auto_barrier_interval"] = instance["config"].get("auto_barrier_interval", "2")
            emu_conf["auto_barrier_pre_cast_delay"] = instance["config"].get("auto_barrier_pre_cast_delay", "0.5")
            emu_conf["auto_barrier_advance_time"] = instance["config"].get("auto_barrier_advance_time", "5.0")
            emu_conf["holy_barrier_duration"] = instance["config"].get("holy_barrier_duration", "180")
            emu_conf["barrier_cast_cooldown"] = instance["config"].get("barrier_cast_cooldown", "60")
            emu_conf["auto_barrier_move_to_cast"] = instance["config"].get("auto_barrier_move_to_cast", False)
            emu_conf["auto_barrier_use_cache"] = instance["config"].get("auto_barrier_use_cache", True)

            emu_conf["auto_barrier_enable_clan_filter"] = instance["config"].get("auto_barrier_enable_clan_filter", False)

            emu_conf["auto_barrier_clan_filter_name"] = instance["config"].get("auto_barrier_clan_filter_name", "")
                   
            all_configs["emulators"].append(emu_conf)
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_configs, f, indent=4, ensure_ascii=False)
            self.log_message(f"[提示] 所有設定已成功儲存到 {CONFIG_FILE}")
        except IOError as e:
            self.log_message(f"[錯誤] 儲存設定檔失敗: {e}")
            messagebox.showerror("儲存失敗", f"無法寫入設定檔: {e}")

    def log_message(self, msg):
        if not self.log_visible:
            return
        def _insert():
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, str(msg) + "\n")
            num_lines = int(self.log_area.index('end-1c').split('.')[0])
            if num_lines > self.MAX_LOG_LINES:
                lines_to_delete = num_lines - self.MAX_LOG_LINES
                self.log_area.delete('1.0', f'{lines_to_delete + 1}.0')
            self.log_area.config(state='disabled')
            self.log_area.see(tk.END)
        if self.root.winfo_exists():
            self.root.after(0, _insert)

    def clear_log(self):
        self.log_area.config(state='normal')
        self.log_area.delete('1.0', tk.END)
        self.log_area.config(state='disabled')

    def on_closing(self):
        try:
            self.save_config()
        except Exception as e:
            print(f"Error saving config on closing: {e}")
        for name, instance in self.instances.items():
            if instance.get("is_monitoring"):
                instance["is_monitoring"] = False
            if instance.get("monitor_thread"):
                instance["monitor_thread"].join(timeout=1)
            if instance.get("is_seq_moving"):
                instance["is_seq_moving"] = False
            if instance.get("seq_move_thread"):
                instance["seq_move_thread"].join(timeout=1)
            if instance.get("is_barrier_running"):
                instance["is_barrier_running"] = False
            if instance.get("barrier_thread"):
                instance["barrier_thread"].join(timeout=1)
            if instance.get("is_monster_detecting"):
                instance["is_monster_detecting"] = False
            if instance.get("monster_detect_thread"):
                instance["monster_detect_thread"].join(timeout=1)
            if instance.get("is_timed_skilling"):
                instance["is_timed_skilling"] = False
            if instance.get("timed_skill_thread"):
                instance["timed_skill_thread"].join(timeout=1)
            if instance.get("is_auto_barrier_running"):
                instance["is_auto_barrier_running"] = False
            if instance.get("auto_barrier_thread"):
                instance["auto_barrier_thread"].join(timeout=1)
            # 自動聚怪
            if instance.get("is_priority_targeting"):
                instance["is_priority_targeting"] = False
            if instance.get("priority_targeting_thread"):
                instance["priority_targeting_thread"].join(timeout=1)
            # 定時指定目標
            if instance.get("is_timed_targeting"):
                instance["is_timed_targeting"] = False
            if instance.get("timed_target_thread"):
                instance["timed_target_thread"].join(timeout=1)
            # 自動巡邏
            if instance.get("is_patrolling"):
                instance["is_patrolling"] = False
            if instance.get("patrol_thread"):
                instance["patrol_thread"].join(timeout=1)
            
            # --- Fix: Explicitly detach session on close ---
            if instance.get("session"):
                try:
                    print(f"Detaching session for {name}...")
                    instance["session"].detach()
                except Exception as e:
                    print(f"Error detaching session for {name}: {e}")
            # -----------------------------------------------

        self.root.destroy()

    def open_adb_commands_dialog(self):
        """開啟 ADB 指令對話框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("ADB 指令工具")
        dialog.transient(self.root)
        dialog.resizable(True, True)
        
        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(3, weight=1)
        
        # --- ADB 路徑設定區域 ---
        path_frame = ttk.LabelFrame(main_frame, text="ADB 路徑設定", padding="10")
        path_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        path_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(path_frame, text="ADB 路徑:").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        adb_path_entry = ttk.Entry(path_frame)
        adb_path_entry.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        
        # 從 config 載入 ADB 路徑
        default_adb_path = "adb"  # 預設使用系統 PATH 中的 adb
        if hasattr(self, 'config'):
            # 嘗試從第一個模擬器配置中獲取 ADB 路徑
            emulators = self.config.get("emulators", [])
            if emulators and len(emulators) > 0:
                default_adb_path = emulators[0].get("adb_path", "C:\\LDPlayer\\LDPlayer9\\adb.exe")
            else:
                default_adb_path = self.config.get("adb_path", "C:\\LDPlayer\\LDPlayer9\\adb.exe")
        
        adb_path_entry.insert(0, default_adb_path)
        
        ttk.Button(path_frame, text="瀏覽", 
                  command=lambda: self.browse_adb_path(adb_path_entry),
                  style='Taller.TButton').grid(row=0, column=2, sticky="ew", padx=2, pady=2)
        
        # --- 基本指令區域 ---
        basic_frame = ttk.LabelFrame(main_frame, text="基本指令", padding="10")
        basic_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        basic_frame.grid_columnconfigure(0, weight=1)
        basic_frame.grid_columnconfigure(1, weight=1)
        
        # 第一行按鈕
        ttk.Button(basic_frame, text="Kill Server", 
                  command=lambda: self.execute_adb_command("kill-server", output_text, adb_path_entry),
                  style='Taller.TButton').grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(basic_frame, text="Start Server", 
                  command=lambda: self.execute_adb_command("start-server", output_text, adb_path_entry),
                  style='Taller.TButton').grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        
        # 第二行按鈕
        ttk.Button(basic_frame, text="Devices", 
                  command=lambda: self.execute_adb_command("devices", output_text, adb_path_entry),
                  style='Taller.TButton').grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(basic_frame, text="Disconnect All", 
                  command=lambda: self.execute_adb_command("disconnect", output_text, adb_path_entry),
                  style='Taller.TButton').grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        
        # --- 連接指令區域 ---
        connect_frame = ttk.LabelFrame(main_frame, text="連接裝置", padding="10")
        connect_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        connect_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(connect_frame, text="IP:Port").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        connect_entry = ttk.Entry(connect_frame)
        connect_entry.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        connect_entry.insert(0, "127.0.0.1:5555")
        
        ttk.Button(connect_frame, text="Connect", 
                  command=lambda: self.execute_adb_command(f"connect {connect_entry.get()}", output_text, adb_path_entry),
                  style='Taller.TButton').grid(row=0, column=2, sticky="ew", padx=2, pady=2)
        
        # --- 端口轉發區域 ---
        forward_frame = ttk.LabelFrame(main_frame, text="端口轉發", padding="10")
        forward_frame.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        forward_frame.grid_columnconfigure(1, weight=1)
        
        # Forward
        ttk.Label(forward_frame, text="Forward (本地→遠端)").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        forward_local_entry = ttk.Entry(forward_frame, width=10)
        forward_local_entry.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        forward_local_entry.insert(0, "27042")
        ttk.Label(forward_frame, text="→").grid(row=0, column=2, padx=2)
        forward_remote_entry = ttk.Entry(forward_frame, width=10)
        forward_remote_entry.grid(row=0, column=3, sticky="w", padx=2, pady=2)
        forward_remote_entry.insert(0, "27042")
        ttk.Button(forward_frame, text="執行", 
                  command=lambda: self.execute_adb_command(
                      f"forward tcp:{forward_local_entry.get()} tcp:{forward_remote_entry.get()}", 
                      output_text, adb_path_entry),
                  style='Taller.TButton').grid(row=0, column=4, sticky="ew", padx=2, pady=2)
        
        # Reverse
        ttk.Label(forward_frame, text="Reverse (遠端→本地)").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        reverse_remote_entry = ttk.Entry(forward_frame, width=10)
        reverse_remote_entry.grid(row=1, column=1, sticky="w", padx=2, pady=2)
        reverse_remote_entry.insert(0, "27042")
        ttk.Label(forward_frame, text="→").grid(row=1, column=2, padx=2)
        reverse_local_entry = ttk.Entry(forward_frame, width=10)
        reverse_local_entry.grid(row=1, column=3, sticky="w", padx=2, pady=2)
        reverse_local_entry.insert(0, "27042")
        ttk.Button(forward_frame, text="執行", 
                  command=lambda: self.execute_adb_command(
                      f"reverse tcp:{reverse_remote_entry.get()} tcp:{reverse_local_entry.get()}", 
                      output_text, adb_path_entry),
                  style='Taller.TButton').grid(row=1, column=4, sticky="ew", padx=2, pady=2)
        
        # Forward 管理按鈕
        forward_mgmt_frame = ttk.Frame(forward_frame)
        forward_mgmt_frame.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(5, 0))
        forward_mgmt_frame.grid_columnconfigure(0, weight=1)
        forward_mgmt_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Button(forward_mgmt_frame, text="列出所有轉發", 
                  command=lambda: self.execute_adb_command("forward --list", output_text, adb_path_entry),
                  style='Taller.TButton').grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(forward_mgmt_frame, text="移除所有轉發", 
                  command=lambda: self.execute_adb_command("forward --remove-all", output_text, adb_path_entry),
                  style='Taller.TButton').grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        
        # --- 輸出區域 ---
        output_frame = ttk.LabelFrame(main_frame, text="執行結果", padding="5")
        output_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 5))
        output_frame.grid_columnconfigure(0, weight=1)
        output_frame.grid_rowconfigure(0, weight=1)
        
        output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, height=15, width=60)
        output_text.grid(row=0, column=0, sticky="nsew")
        
        # --- 底部按鈕 ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, sticky="ew")
        
        ttk.Button(button_frame, text="清除輸出", 
                  command=lambda: output_text.delete("1.0", tk.END),
                  style='Taller.TButton').pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="關閉", 
                  command=dialog.destroy,
                  style='Taller.TButton').pack(side=tk.RIGHT, padx=2)
        
        # 設定視窗大小和位置
        self.root.update_idletasks()
        dialog_width = 450
        dialog_height = 630
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")
        
        # 初始訊息
        output_text.insert("1.0", "ADB 指令工具已就緒\n" + "="*50 + "\n\n")

    def execute_adb_command(self, adb_args, output_widget, adb_path_entry):
        """執行 ADB 指令並顯示結果"""
        try:
            # 獲取 ADB 路徑
            adb_path = adb_path_entry.get().strip()
            if not adb_path:
                adb_path = "adb"
            
            # 構建完整指令
            if adb_path.lower().endswith("adb.exe") or adb_path.lower().endswith("adb"):
                # 如果是完整路徑,直接使用
                full_command = f'"{adb_path}" {adb_args}'
            else:
                # 如果只是 "adb",直接使用
                full_command = f"{adb_path} {adb_args}"
            
            output_widget.insert(tk.END, f"\n> 執行指令: {full_command}\n")
            output_widget.see(tk.END)
            output_widget.update()
            
            # 執行指令
            result = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )
            
            # 顯示輸出
            if result.stdout:
                output_widget.insert(tk.END, result.stdout)
            if result.stderr:
                output_widget.insert(tk.END, f"[錯誤] {result.stderr}")
            
            # 顯示返回碼
            if result.returncode == 0:
                output_widget.insert(tk.END, f"✓ 指令執行成功 (返回碼: {result.returncode})\n")
            else:
                output_widget.insert(tk.END, f"✗ 指令執行失敗 (返回碼: {result.returncode})\n")
            
            output_widget.insert(tk.END, "-"*50 + "\n")
            output_widget.see(tk.END)
            
        except subprocess.TimeoutExpired:
            output_widget.insert(tk.END, "[錯誤] 指令執行逾時 (超過30秒)\n")
            output_widget.insert(tk.END, "-"*50 + "\n")
            output_widget.see(tk.END)
        except FileNotFoundError:
            adb_path = adb_path_entry.get().strip() if adb_path_entry else "adb"
            output_widget.insert(tk.END, f"[錯誤] 找不到 ADB 執行檔: {adb_path}\n")
            output_widget.insert(tk.END, "請確認 ADB 路徑是否正確,或將 ADB 加入系統 PATH。\n")
            output_widget.insert(tk.END, "-"*50 + "\n")
            output_widget.see(tk.END)
        except Exception as e:
            output_widget.insert(tk.END, f"[錯誤] 執行失敗: {str(e)}\n")
            output_widget.insert(tk.END, "-"*50 + "\n")
            output_widget.see(tk.END)

    def browse_adb_path(self, entry_widget):
        """開啟檔案瀏覽對話框選擇 ADB 執行檔"""
        filename = filedialog.askopenfilename(
            title="選擇 ADB 執行檔",
            filetypes=[("ADB 執行檔", "adb.exe"), ("所有檔案", "*.*")]
        )
        if filename:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)

    def check_port_forward_status(self, name, local_port, remote_port):
        """檢查指定的端口轉發是否已建立"""
        try:
            instance = self.instances[name]
            ui = instance["ui"]
            adb_path = ui["adb_path_entry"].get().strip()
            device_serial = ui["device_serial_entry"].get().strip()
            
            if not adb_path:
                adb_path = "adb"
            
            # 構建指令
            if device_serial:
                cmd = f'"{adb_path}" -s {device_serial} forward --list'
            else:
                cmd = f'"{adb_path}" forward --list'
            
            # 執行指令
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                # 解析輸出,檢查是否包含指定的端口轉發
                # 格式通常是: <serial> tcp:<local_port> tcp:<remote_port>
                output = result.stdout
                forward_pattern = f"tcp:{local_port} tcp:{remote_port}"
                return forward_pattern in output
            else:
                self.log_message(f"[{name}] 檢查端口轉發失敗: {result.stderr}")
                return False
                
        except Exception as e:
            self.log_message(f"[{name}] 檢查端口轉發時發生錯誤: {e}")
            return False

    def setup_port_forward(self, name, local_port, remote_port):
        """建立端口轉發"""
        try:
            instance = self.instances[name]
            ui = instance["ui"]
            adb_path = ui["adb_path_entry"].get().strip()
            device_serial = ui["device_serial_entry"].get().strip()
            
            if not adb_path:
                adb_path = "adb"
            
            # 構建指令
            if device_serial:
                cmd = f'"{adb_path}" -s {device_serial} forward tcp:{local_port} tcp:{remote_port}'
            else:
                cmd = f'"{adb_path}" forward tcp:{local_port} tcp:{remote_port}'
            
            self.log_message(f"[{name}] 正在建立端口轉發: {local_port} → {remote_port}")
            
            # 執行指令
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                self.log_message(f"[{name}] ✓ 端口轉發建立成功")
                # 更新 UI 狀態
                if "forward_status_label" in ui and ui["forward_status_label"].winfo_exists():
                    ui["forward_status_label"].config(text="● 端口轉發", foreground="green")
                return True
            else:
                self.log_message(f"[{name}] ✗ 端口轉發建立失敗: {result.stderr}")
                return False
                
        except Exception as e:
            self.log_message(f"[{name}] 建立端口轉發時發生錯誤: {e}")
            return False

    def start_frida_setup_thread(self, name):
        """啟動 Frida 與端口轉發的線程包裝"""
        thread = threading.Thread(target=self._start_frida_setup, args=(name,), daemon=True)
        thread.start()

    def _start_frida_setup(self, name):
        """啟動 Frida 伺服器並設定端口轉發"""
        try:
            instance = self.instances[name]
            ui = instance["ui"]
            
            # 獲取設定
            device_serial = ui["device_serial_entry"].get().strip()
            forward_port = ui["forward_port_entry"].get().strip()
            
            if not forward_port:
                self.log_message(f"[{name}] 錯誤:請輸入轉發端口")
                messagebox.showerror("錯誤", "請輸入轉發端口")
                return
            
            try:
                forward_port = int(forward_port)
            except ValueError:
                self.log_message(f"[{name}] 錯誤:轉發端口必須是數字")
                messagebox.showerror("錯誤", "轉發端口必須是數字")
                return
            
            self.log_message(f"[{name}] === 開始 Frida 環境設定 ===")
            
            # 步驟 1: 檢查端口轉發狀態
            self.log_message(f"[{name}] 檢查端口轉發狀態...")
            forward_exists = self.check_port_forward_status(name, forward_port, forward_port)
            
            if forward_exists:
                self.log_message(f"[{name}] ✓ 端口轉發已存在")
            else:
                self.log_message(f"[{name}] ⚠ 端口轉發不存在,正在建立...")
                # 建立端口轉發
                if not self.setup_port_forward(name, forward_port, forward_port):
                    self.log_message(f"[{name}] ✗ 端口轉發建立失敗,請檢查 ADB 連接")
                    messagebox.showerror("錯誤", "端口轉發建立失敗\n請檢查:\n1. ADB 路徑是否正確\n2. 裝置是否已連接\n3. 端口是否被占用")
                    return
            
            # 步驟 2: 檢查 Frida 伺服器狀態
            # 這裡可以添加檢查 Frida 是否運行的邏輯
            # 例如:執行 adb shell "ps | grep frida-server"
            
            self.log_message(f"[{name}] === Frida 環境設定完成 ===")
            self.log_message(f"[{name}] 端口轉發: localhost:{forward_port} → device:{forward_port}")
            
            # 更新 UI 狀態
            if "forward_status_label" in ui and ui["forward_status_label"].winfo_exists():
                def update_ui():
                    ui["forward_status_label"].config(text="● 端口轉發", foreground="green")
                self.root.after(0, update_ui)
            
            messagebox.showinfo("成功", f"Frida 環境設定完成\n端口轉發: {forward_port} → {forward_port}")
            
        except Exception as e:
            self.log_message(f"[{name}] Frida 設定過程發生錯誤: {e}")
            messagebox.showerror("錯誤", f"Frida 設定失敗:\n{str(e)}")

    def open_auto_barrier_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 自動聖結界設定")
        dialog.transient(self.root)
        # dialog.grab_set()  # 註解掉以允許同時操作主介面
        # 延後設定視窗位置,等UI元件創建完成後再設定

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)

        # --- Top Control Frame ---
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        load_players_button = ttk.Button(control_frame, text="載入周圍玩家", command=lambda: self._load_players_for_selection_dialog(name, dialog), style='Taller.TButton')
        load_players_button.pack(side=tk.LEFT, fill=tk.X, expand=True)

        clan_filter_frame = ttk.Frame(control_frame)
        clan_filter_frame.pack(fill=tk.X, pady=(5,0))

        ui["auto_barrier_enable_clan_filter_var"] = tk.BooleanVar()
        ttk.Checkbutton(clan_filter_frame, text="血盟過濾", variable=ui["auto_barrier_enable_clan_filter_var"]).pack(side=tk.LEFT)

        ui["auto_barrier_clan_filter_entry"] = ttk.Entry(clan_filter_frame, width=15)
        ui["auto_barrier_clan_filter_entry"].pack(side=tk.LEFT, padx=(5,0))

        # Load initial values for clan filter
        ui["auto_barrier_enable_clan_filter_var"].set(instance["config"].get("auto_barrier_enable_clan_filter", False))
        ui["auto_barrier_clan_filter_entry"].insert(0, instance["config"].get("auto_barrier_clan_filter_name", ""))

        # --- Target List Frame ---
        list_frame = ttk.LabelFrame(main_frame, text="施法目標列表 (每行一位)")
        list_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        barrier_targets_text = scrolledtext.ScrolledText(list_frame, wrap=tk.WORD, height=10)
        barrier_targets_text.grid(row=0, column=0, sticky="nsew")
        
        # Store widget in ui for later access
        ui["barrier_targets_text"] = barrier_targets_text

        # --- Bottom Control Frame ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        bottom_frame.grid_columnconfigure(0, weight=1)

        toggle_frame = ttk.Frame(bottom_frame)
        toggle_frame.pack(fill=tk.X, expand=True, pady=(0, 5))

        # Row 1: Toggle Button and Interval
        row1_frame = ttk.Frame(toggle_frame)
        row1_frame.pack(fill=tk.X, pady=(0, 2))
        
        toggle_button = ttk.Button(row1_frame, text="開始", command=lambda: self.toggle_auto_holy_barrier(name, toggle_button, interval_entry), style='Taller.TButton')
        toggle_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ui["auto_barrier_toggle_button"] = toggle_button # Store button reference

        ttk.Label(row1_frame, text="間隔(秒):").pack(side=tk.LEFT)
        interval_entry = ttk.Entry(row1_frame, width=5)
        interval_entry.pack(side=tk.LEFT)

        # Row 2: Delays and Advance Time
        row2_frame = ttk.Frame(toggle_frame)
        row2_frame.pack(fill=tk.X, pady=(2, 0))

        ttk.Label(row2_frame, text="施法延遲:").pack(side=tk.LEFT)
        pre_cast_delay_entry = ttk.Entry(row2_frame, width=5)
        pre_cast_delay_entry.pack(side=tk.LEFT, padx=(0, 10))
        ui["auto_barrier_pre_cast_delay_entry"] = pre_cast_delay_entry # Store widget in ui

        ttk.Label(row2_frame, text="提前施放:").pack(side=tk.LEFT)
        advance_time_entry = ttk.Entry(row2_frame, width=5)
        advance_time_entry.pack(side=tk.LEFT)
        ui["auto_barrier_advance_time_entry"] = advance_time_entry # Store widget in ui

        # Row 3: Buff Duration and Cast Cooldown
        row3_frame = ttk.Frame(toggle_frame)
        row3_frame.pack(fill=tk.X, pady=(2, 0))

        ttk.Label(row3_frame, text="Buff持續:").pack(side=tk.LEFT)
        buff_duration_entry = ttk.Entry(row3_frame, width=5)
        buff_duration_entry.pack(side=tk.LEFT, padx=(0, 10))
        ui["auto_barrier_buff_duration_entry"] = buff_duration_entry

        ttk.Label(row3_frame, text="施法冷卻:").pack(side=tk.LEFT)
        cast_cooldown_entry = ttk.Entry(row3_frame, width=5)
        cast_cooldown_entry.pack(side=tk.LEFT)
        ui["auto_barrier_cast_cooldown_entry"] = cast_cooldown_entry

        # Row 4: Move to Cast Checkbox
        row4_frame = ttk.Frame(toggle_frame)
        row4_frame.pack(fill=tk.X, pady=(2, 0))

        ui["auto_barrier_move_to_cast_var"] = tk.BooleanVar()
        ttk.Checkbutton(row4_frame, text="移動施放 (失敗時移動到目標位置)", 
                        variable=ui["auto_barrier_move_to_cast_var"]).pack(side=tk.LEFT)

        # Row 5: Use Cache Checkbox
        row5_frame = ttk.Frame(toggle_frame)
        row5_frame.pack(fill=tk.X, pady=(2, 0))

        ui["auto_barrier_use_cache_var"] = tk.BooleanVar()
        ttk.Checkbutton(row5_frame, text="使用快取時間 (API無資訊時依快取判斷)", 
                        variable=ui["auto_barrier_use_cache_var"]).pack(side=tk.LEFT)

        save_button = ttk.Button(bottom_frame, text="儲存", style='Taller.TButton')
        save_button.pack(fill=tk.X, expand=True)

        # --- Logic for closing and saving ---
        def save_and_close():
            # Save data to instance config
            instance["config"]["auto_barrier_targets"] = ui["barrier_targets_text"].get("1.0", tk.END).strip()
            instance["config"]["auto_barrier_interval"] = interval_entry.get()
            instance["config"]["auto_barrier_enable_clan_filter"] = ui["auto_barrier_enable_clan_filter_var"].get()
            instance["config"]["auto_barrier_clan_filter_name"] = ui["auto_barrier_clan_filter_entry"].get()
            instance["config"]["auto_barrier_pre_cast_delay"] = ui["auto_barrier_pre_cast_delay_entry"].get() # Save new setting
            instance["config"]["auto_barrier_advance_time"] = ui["auto_barrier_advance_time_entry"].get() # Save advance time setting
            instance["config"]["holy_barrier_duration"] = ui["auto_barrier_buff_duration_entry"].get() # Save buff duration
            instance["config"]["barrier_cast_cooldown"] = ui["auto_barrier_cast_cooldown_entry"].get() # Save cast cooldown
            instance["config"]["auto_barrier_move_to_cast"] = ui["auto_barrier_move_to_cast_var"].get() # Save move to cast setting
            instance["config"]["auto_barrier_use_cache"] = ui["auto_barrier_use_cache_var"].get() # Save use cache setting
            self.log_message(f"[{name}] 已儲存自動聖結界設定。")

        save_button.config(command=save_and_close)

        # --- Load initial data ---
        barrier_targets_text.insert("1.0", instance["config"].get("auto_barrier_targets", ""))
        interval_entry.insert(0, instance["config"].get("auto_barrier_interval", "2"))
        ui["auto_barrier_pre_cast_delay_entry"].insert(0, instance["config"].get("auto_barrier_pre_cast_delay", "0.5")) # Load new setting
        ui["auto_barrier_advance_time_entry"].insert(0, instance["config"].get("auto_barrier_advance_time", "5.0")) # Load advance time setting
        ui["auto_barrier_buff_duration_entry"].insert(0, instance["config"].get("holy_barrier_duration", "180")) # Load buff duration
        ui["auto_barrier_cast_cooldown_entry"].insert(0, instance["config"].get("barrier_cast_cooldown", "60")) # Load cast cooldown
        ui["auto_barrier_move_to_cast_var"].set(instance["config"].get("auto_barrier_move_to_cast", False)) # Load move to cast setting
        ui["auto_barrier_use_cache_var"].set(instance["config"].get("auto_barrier_use_cache", True)) # Load use cache setting

        # --- Set initial button states ---
        if instance.get("is_auto_barrier_running", False):
            toggle_button.config(text="停止")

        if not instance.get("script_api"):
            load_players_button.config(state='disabled')
            toggle_button.config(state='disabled')

        # 所有UI元件創建完成後,設定視窗位置並顯示
        self.root.update_idletasks()
        dialog_width = 320
        dialog_height = 450
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)

    def _load_players_for_selection_dialog(self, name, parent_dialog):
        instance = self.instances[name]
        api = instance.get("script_api")
        if not api:
            messagebox.showwarning("未連接", "Frida尚未連接，無法獲取玩家列表。", parent=parent_dialog)
            return

        try:
            self.log_message(f"[{name}] 正在讀取周圍玩家...")

            ui = instance["ui"]
            use_manual_filter = ui["auto_barrier_enable_clan_filter_var"].get()
            manual_clan_name = ui["auto_barrier_clan_filter_entry"].get().strip()

            target_clan_name = ""
            filter_by_clan = False

            if use_manual_filter and manual_clan_name:
                target_clan_name = manual_clan_name
                filter_by_clan = True
                self.log_message(f"[{name}] 啟用手動血盟過濾: '{target_clan_name}'。")
            else:
                self.log_message(f"[{name}] 未啟用手動血盟過濾，將載入所有玩家。")
                filter_by_clan = False


            # --- 2. Get surrounding objects ---
            world_info_str = api.get_info(203)
            if not world_info_str:
                raise Exception("獲取周圍物件失敗 (RPC get_info(203) 未返回任何資料)")

            world_json = json.loads(world_info_str)
            all_objects = world_json.get('data', [])

            # --- 3. Filter for allied players ---
            filtered_players = []
            for obj in all_objects:
                obj_type = obj.get("type")
                obj_name = obj.get("name")
                obj_clan_name = obj.get("clanName", '').strip()

                if obj_type == 2 and obj_name: # It's a player and has a name
                    if filter_by_clan:
                        if obj_clan_name == target_clan_name: # Use the determined target_clan_name
                            filtered_players.append(obj_name)
                    else: # No clan filtering
                        filtered_players.append(obj_name)
            
            players = sorted(list(set(filtered_players)), key=str.lower) # Use set to remove duplicates, then sort

            if not players:
                messagebox.showinfo("無玩家", "周圍未偵測到任何符合條件的玩家。", parent=parent_dialog)
                return

            # --- Create selection dialog ---
            selection_dialog = tk.Toplevel(parent_dialog)
            selection_dialog.title("選擇要加入的玩家")
            selection_dialog.transient(parent_dialog)
            selection_dialog.grab_set()
            selection_dialog.geometry("300x400")

            # Center the dialog
            selection_dialog.update_idletasks()
            dialog_width = 300
            dialog_height = 400
            parent_x = parent_dialog.winfo_x()
            parent_y = parent_dialog.winfo_y()
            parent_width = parent_dialog.winfo_width()
            parent_height = parent_dialog.winfo_height()
            center_x = parent_x + (parent_width - dialog_width) // 2
            center_y = parent_y + (parent_height - dialog_height) // 2
            selection_dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

            listbox_frame = ttk.Frame(selection_dialog, padding="10")
            listbox_frame.pack(expand=True, fill=tk.BOTH)
            
            listbox = Listbox(listbox_frame, selectmode=tk.MULTIPLE, exportselection=False)
            listbox.pack(expand=True, fill=tk.BOTH)

            for player_name in players:
                listbox.insert(tk.END, player_name)

            def add_selected():
                selected_indices = listbox.curselection()
                selected_players = {listbox.get(i) for i in selected_indices}

                # Get existing players
                target_text_widget = instance["ui"]["barrier_targets_text"]
                current_players_str = target_text_widget.get("1.0", tk.END).strip()
                current_players = {line.strip() for line in current_players_str.split('\n') if line.strip()}
                
                # Add new players, avoiding duplicates
                new_players_to_add = selected_players - current_players
                
                if new_players_to_add:
                    # Append with a newline if there's existing text
                    prefix = "\n" if current_players_str else ""
                    target_text_widget.insert(tk.END, prefix + "\n".join(sorted(list(new_players_to_add))))
                
                self.log_message(f"[{name}] 已新增 {len(new_players_to_add)} 名玩家到聖結界列表。")
                selection_dialog.destroy()

            button_frame = ttk.Frame(selection_dialog, padding=(10,0,10,10))
            button_frame.pack(fill=tk.X)
            add_button = ttk.Button(button_frame, text="新增選取項目", command=add_selected)
            add_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,5))
            cancel_button = ttk.Button(button_frame, text="取消", command=selection_dialog.destroy)
            cancel_button.pack(side=tk.LEFT, expand=True, fill=tk.X)

        except Exception as e:
            self.log_message(f"[{name}] 載入周圍玩家時發生錯誤: {e}")
            messagebox.showerror("錯誤", f"載入周圍玩家時發生錯誤: {e}", parent=parent_dialog)

    def toggle_auto_holy_barrier(self, name, toggle_button, interval_entry):
        instance = self.instances[name]
        ui = instance["ui"]

        if instance["is_auto_barrier_running"]:
            instance["is_auto_barrier_running"] = False
            self.log_message(f"[{name}] --- 正在停止自動聖結界... ---")
            if toggle_button.winfo_exists():
                toggle_button.config(state='disabled', text="停止中...")
            return

        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        try:
            interval = float(interval_entry.get())
            if interval <= 0:
                raise ValueError("間隔必須大於 0")
            
            target_list_str = ui["barrier_targets_text"].get("1.0", tk.END).strip()
            if not target_list_str:
                return messagebox.showwarning(f"[{name}] 設定錯誤", "目標列表不能為空。")

        except ValueError as e:
            return messagebox.showerror(f"[{name}] 輸入錯誤", f"間隔無效: {e}")

        # Ensure the latest target list from the UI is saved to config before starting the loop
        instance["config"]["auto_barrier_targets"] = ui["barrier_targets_text"].get("1.0", tk.END).strip()

        instance["is_auto_barrier_running"] = True
        if toggle_button.winfo_exists():
            toggle_button.config(text="停止")
        
        instance["auto_barrier_thread"] = threading.Thread(target=self.auto_holy_barrier_loop, args=(name, interval), daemon=True)
        instance["auto_barrier_thread"].start()

    def auto_holy_barrier_loop(self, name, interval):
        instance = self.instances[name]
        ui = instance["ui"]
        api = instance["script_api"]
        
        # TODO: Make this configurable
        HOLY_BARRIER_CAST_ID = 333 # 聖結界施法ID (假設)
        HOLY_BARRIER_BUFF_ID = 333    # 聖結界Buff ID

        self.log_message(f"--- [{name}] 開始自動聖結界 (間隔 {interval}s) ---")

        # 初始化 Buff 快取字典
        if "barrier_buff_cache" not in instance:
            instance["barrier_buff_cache"] = {}
            # 結構: {player_name: {"buff_expire_time": timestamp, "last_cast_time": timestamp}}
        
        # 獲取設定參數
        buff_duration = float(instance["config"].get("holy_barrier_duration", "180"))  # Buff 持續時間(秒)
        cast_cooldown = float(instance["config"].get("barrier_cast_cooldown", "60"))  # 施法冷卻(秒)

        try:
            while instance["is_auto_barrier_running"]:
                target_names_str = instance["config"].get("auto_barrier_targets", "")
                target_names = {name.strip() for name in target_names_str.splitlines() if name.strip()}
                
                if not target_names:
                    self.log_message(f"[{name}] 自動聖結界列表為空，暫停。")
                    time.sleep(interval)
                    continue

                current_time = time.time()

                # 獲取玩家自己的位置
                player_info_str = api.get_info(201)
                player_x, player_y = None, None
                if player_info_str:
                    try:
                        player_data = json.loads(player_info_str)
                        player_info = player_data.get('data', player_data)
                        player_x = player_info.get('x')
                        player_y = player_info.get('y')
                    except:
                        pass

                world_info_str = api.get_info(203)
                if not world_info_str:
                    self.log_message(f"[{name}] 自動聖結界: 無法獲取周圍物件。")
                    time.sleep(interval)
                    continue
                
                world_json = json.loads(world_info_str)
                all_objects = world_json.get('data', [])


                for obj in all_objects:
                    if not instance["is_auto_barrier_running"]: break
                    
                    obj_name = obj.get("name")
                    if obj.get("type") != 2 or obj_name not in target_names:
                        continue
                    
                    # 初始化該玩家的快取
                    if obj_name not in instance["barrier_buff_cache"]:
                        instance["barrier_buff_cache"][obj_name] = {
                            "buff_expire_time": 0,
                            "last_cast_time": 0
                        }
                    
                    cache = instance["barrier_buff_cache"][obj_name]
                    
                    # 檢查 API 回傳的 Buff 狀態
                    buffs = obj.get("buff", [])
                    has_buff_in_api = False
                    api_buff_remain_time = 0
                    
                    # 先檢查是否啟用快取 (優先從 UI 讀取,實現即時生效)
                    ui = instance["ui"]
                    if "auto_barrier_use_cache_var" in ui:
                        try:
                            use_cache = ui["auto_barrier_use_cache_var"].get()
                        except:
                            use_cache = instance["config"].get("auto_barrier_use_cache", True)
                    else:
                        use_cache = instance["config"].get("auto_barrier_use_cache", True)
                    # Debug: 顯示快取設定 (每個玩家只顯示一次)
                    if obj_name not in instance.get("_cache_setting_logged", set()):
                        self.log_message(f"[{name}] DEBUG: '{obj_name}' 使用快取時間設定 = {use_cache}")
                        if "_cache_setting_logged" not in instance:
                            instance["_cache_setting_logged"] = set()
                        instance["_cache_setting_logged"].add(obj_name)

                    for b in buffs:
                        if b.get("skillID") == HOLY_BARRIER_BUFF_ID:
                            has_buff_in_api = True
                            api_buff_remain_time = b.get("remainTime", 0)
                            # 只在啟用快取時更新快取的過期時間
                            if use_cache:
                                cache["buff_expire_time"] = current_time + (api_buff_remain_time / 1000)
                            break
                    
                    # 判斷是否需要施法
                    should_cast = False
                    reason = ""
                    
                    if has_buff_in_api:
                        # API 有回傳 Buff,檢查是否快過期
                        advance_time_sec = float(instance["config"].get("auto_barrier_advance_time", "5.0"))
                        advance_time_ms = advance_time_sec * 1000
                        
                        if api_buff_remain_time < advance_time_ms:
                            should_cast = True
                            reason = f"Buff 時間過低 ({api_buff_remain_time/1000:.1f}s < {advance_time_sec}s)"
                        
                        # 重置跳過日誌標記 (因為 API 有回傳 Buff)
                        if use_cache:
                            cache["skip_logged"] = False
                    else:
                        # API 沒有回傳 Buff
                        
                        if use_cache:
                            # 使用快取判斷
                            advance_time_sec = float(instance["config"].get("auto_barrier_advance_time", "5.0"))
                            remain_cached = cache["buff_expire_time"] - current_time
                            
                            # 檢查是否需要施法 (過期或即將過期)
                            if remain_cached < advance_time_sec:
                                should_cast = True
                                if remain_cached <= 0:
                                    reason = "快取顯示 Buff 已過期"
                                else:
                                    reason = f"快取顯示 Buff 即將過期 ({remain_cached:.1f}s < {advance_time_sec}s)"
                                cache["skip_logged"] = False  # 重置標記
                            else:
                                # 快取顯示 Buff 還有足夠時間
                                # 只在首次跳過時記錄日誌
                                if not cache.get("skip_logged", False):
                                    self.log_message(f"[{name}] '{obj_name}' API 無 Buff 資訊,但快取顯示還有 {remain_cached:.1f}s,跳過施法")
                                    cache["skip_logged"] = True
                                
                                continue
                        else:
                            # 不使用快取,直接施法
                            should_cast = True
                            reason = "API 無 Buff 資訊且未啟用快取判斷"

                    
                    # 檢查施法冷卻
                    if should_cast:
                        time_since_last_cast = current_time - cache["last_cast_time"]
                        if time_since_last_cast < cast_cooldown:
                            self.log_message(f"[{name}] '{obj_name}' 冷卻中 (剩餘 {cast_cooldown - time_since_last_cast:.0f}s)")
                            continue
                        
                        # 記錄原因
                        self.log_message(f"[{name}] '{obj_name}' 需要施法: {reason}")
                        
                        # 執行施法邏輯 (保留原有變數名稱以相容後續程式碼)
                        has_buff = has_buff_in_api
                        is_buff_low = should_cast
                        target_key = obj.get("objectKey")
                        target_name = obj.get("name")
                        target_x = obj.get("x")
                        target_y = obj.get("y")
                        
                        # 計算方位和距離
                        direction_info = ""
                        if player_x is not None and player_y is not None and target_x is not None and target_y is not None:
                            import math
                            dx = target_x - player_x
                            dy = target_y - player_y
                            
                            distance = math.sqrt(dx**2 + dy**2)
                            
                            # 計算角度 (0~360度)
                            angle = math.degrees(math.atan2(dy, dx))
                            if angle < 0:
                                angle += 360
                            
                            if abs(dx) < 1 and abs(dy) < 1:
                                direction = "同位置"
                            else:
                                # 定義角度區間 (角度為 0~360)
                                if angle >= 346.7 or angle < 13.3:
                                    direction = "右上 ↗"
                                elif 13.3 <= angle < 58.3:
                                    direction = "正右 →"
                                elif 58.3 <= angle < 121.7:
                                    direction = "右下 ↘"
                                elif 121.7 <= angle < 166.7:
                                    direction = "正下 ↓"
                                elif 166.7 <= angle < 193.3:
                                    direction = "左下 ↙"
                                elif 193.3 <= angle < 238.3:
                                    direction = "正左 ←"
                                elif 238.3 <= angle < 301.7:
                                    direction = "左上 ↖"
                                else: # 301.7 <= angle < 346.7
                                    direction = "正上 ↑"
                            
                            direction_info = f" [{direction}, 距離: {distance:.0f}]"
                        
                        log_prefix = f"[{name}] "
                        if not has_buff:
                            self.log_message(f"{log_prefix}偵測到 '{target_name}'{direction_info} 沒有聖結界，準備施放。")
                        else:
                            self.log_message(f"{log_prefix}正在為 '{target_name}'{direction_info} 重新施放聖結界。")

                        cast_successful = False
                        for attempt in range(5): # 最多重試5次
                            self.log_message(f"{log_prefix}正在對 '{target_name}'{direction_info} 進行第 {attempt + 1} 次施法...")
                            
                            # 施法前延遲(如果有設定)
                            pre_cast_delay = float(instance["config"].get("auto_barrier_pre_cast_delay", "0.5"))
                            if pre_cast_delay > 0:
                                time.sleep(pre_cast_delay)
                            
                            # 直接對目標施放技能,不需要先 set_target
                            skill_cast_result = api.use_skill(HOLY_BARRIER_CAST_ID, str(target_key))
                            self.log_message(f"{log_prefix}施法結果: {skill_cast_result}")
                            
                            # 施法後等待遊戲狀態更新
                            time.sleep(1.0) # 增加等待時間以確保狀態更新

                            # 重新獲取周圍物件來驗證
                            verification_world_info_str = api.get_info(203)
                            if not verification_world_info_str:
                                self.log_message(f"{log_prefix}驗證失敗:無法獲取物件資訊。")
                                continue # 繼續下一次嘗試

                            verification_world_json = json.loads(verification_world_info_str)
                            verification_objects = verification_world_json.get('data', [])
                            
                            target_found_and_buffed = False
                            for v_obj in verification_objects:
                                if v_obj.get("objectKey") == target_key:
                                    v_buffs = v_obj.get("buff", [])
                                    for v_buff in v_buffs:
                                        # 檢查 buff ID 且剩餘時間大於一個很小的值,避免剛加上就消失的誤判
                                        if v_buff.get("skillID") == HOLY_BARRIER_BUFF_ID and v_buff.get("remainTime", 0) > 1000:
                                            target_found_and_buffed = True
                                            break
                                    break # 找到目標物件後就不用再找了

                            if target_found_and_buffed:
                                self.log_message(f"{log_prefix}成功為 '{target_name}' 施放聖結界。")
                                cast_successful = True
                                break # 成功,跳出重試迴圈
                            else:
                                self.log_message(f"{log_prefix}第 {attempt + 1} 次施法後,未在 '{target_name}' 身上偵測到聖結界。")
                                
                                
                                # 如果是第一次失敗且啟用移動施放 (優先從 UI 讀取,實現即時生效)
                                if "auto_barrier_move_to_cast_var" in ui:
                                    try:
                                        move_to_cast_enabled = ui["auto_barrier_move_to_cast_var"].get()
                                    except:
                                        move_to_cast_enabled = instance["config"].get("auto_barrier_move_to_cast", False)
                                else:
                                    move_to_cast_enabled = instance["config"].get("auto_barrier_move_to_cast", False)
                                
                                if attempt == 0 and move_to_cast_enabled:
                                    self.log_message(f"{log_prefix}移動施放已啟用,正在移動到 '{target_name}' 的位置 ({target_x}, {target_y})...")
                                    try:
                                        move_result = api.moveto(target_x, target_y)
                                        self.log_message(f"{log_prefix}移動結果: {move_result}")
                                        time.sleep(2.5)  # 等待移動完成
                                    except Exception as move_error:
                                        self.log_message(f"{log_prefix}移動失敗: {move_error}")
                                elif attempt < 4:
                                    time.sleep(0.5) # 每次重試之間稍作等待

                        if not cast_successful:
                            self.log_message(f"{log_prefix}對 '{target_name}' 施法 5 次後均失敗。")
                        
                        # 更新快取 (不論成功失敗都更新,避免重複嘗試)
                        cache["last_cast_time"] = current_time
                        cache["buff_expire_time"] = current_time + buff_duration
                        
                        time.sleep(0.5) # 完成一個玩家的處理後,不論成功失敗都等待一下

                # Main loop sleep
                sleep_end_time = time.time() + interval
                while time.time() < sleep_end_time:
                    if not instance["is_auto_barrier_running"]:
                        break
                    time.sleep(0.1)

        except Exception as e:
            if instance["is_auto_barrier_running"]:
                self.log_message(f"[{name}] 自動聖結界迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] 自動聖結界結束 ---")
            if self.root.winfo_exists() and name in self.instances:
                def _reset_ui():
                    instance["is_auto_barrier_running"] = False
                    if "auto_barrier_toggle_button" in ui and ui["auto_barrier_toggle_button"].winfo_exists():
                        ui["auto_barrier_toggle_button"].config(state='normal', text="開始")
                self.root.after(0, _reset_ui)



    def toggle_timed_skill(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        if instance["is_timed_skilling"]:
            instance["is_timed_skilling"] = False
            self.log_message(f"[{name}] --- 正在停止定時施法... ---")
            ui["timed_skill_button"].config(state='disabled', text="停止中...")
            return

        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        try:
            interval = float(ui["timed_skill_interval_entry"].get())
            if interval <= 0:
                raise ValueError("間隔必須大於 0")
            skill_id_str = ui["skill_id_entry"].get().strip()
            if not skill_id_str.isdigit():
                return messagebox.showwarning(f"[{name}] 輸入錯誤", "技能 ID 必須是數字。")
            skill_id = int(skill_id_str)

        except ValueError as e:
            return messagebox.showerror(f"[{name}] 輸入錯誤", f"間隔或技能ID無效: {e}")

        instance["is_timed_skilling"] = True
        ui["timed_skill_button"].config(text="停止定時")
        instance["timed_skill_thread"] = threading.Thread(target=self.timed_skill_loop, args=(name, skill_id, interval), daemon=True)
        instance["timed_skill_thread"].start()

    def timed_skill_loop(self, name, skill_id, interval):
        instance = self.instances[name]
        ui = instance["ui"]
        self.log_message(f"--- [{name}] 開始定時施放技能 ID: {skill_id} (間隔 {interval}s) ---")

        try:
            while instance["is_timed_skilling"]:
                target_key = "0"
                
                self.log_message(f"[{name}] 定時施法: 執行一次技能 {skill_id}...")
                self.execute_use_skill(name, skill_id, target_key, update_ui=False)
                
                sleep_end_time = time.time() + interval
                while time.time() < sleep_end_time:
                    if not instance["is_timed_skilling"]:
                        break
                    time.sleep(0.1)

        except Exception as e:
            if instance["is_timed_skilling"]:
                self.log_message(f"[{name}] 定時施法迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] 定時施法結束 ---")
            if self.root.winfo_exists() and name in self.instances:
                def _reset_ui():
                    instance["is_timed_skilling"] = False
                    ui["timed_skill_button"].config(state='normal', text="定時施法")
                self.root.after(0, _reset_ui)

    def create_independent_control_tab(self):
        tab_frame = ttk.Frame(self.notebook, padding="2")
        self.notebook.add(tab_frame, text="獨立控制")
        
        # Configure grid columns for equal width
        tab_frame.grid_columnconfigure(0, weight=1)
        tab_frame.grid_columnconfigure(1, weight=1)
        tab_frame.grid_columnconfigure(2, weight=1)
        
        # Configure grid rows
        tab_frame.grid_rowconfigure(0, weight=0)  # Global control row (fixed height)
        tab_frame.grid_rowconfigure(1, weight=1)  # Individual controls row (expandable)
        
        # ==================== 全域控制區域 ====================
        global_control_frame = ttk.LabelFrame(tab_frame, text="全域控制", padding="5")
        global_control_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=2, pady=(2, 5))
        
        # ==================== 參數設定區域 (第一行) ====================
        settings_frame = ttk.Frame(global_control_frame)
        settings_frame.pack(fill=tk.X, padx=5, pady=2)
        
        # 嘗試從設定載入預設值
        global_settings = getattr(self, "config", {}).get("global_settings", {})

        # 區塊選擇
        saved_instance = global_settings.get("monster_hp_detection_instance", "自動選擇")
        self.detection_instance_var = tk.StringVar(value=saved_instance)
        self.detection_instance_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.detection_instance_var,
            state="readonly",
            width=8,
            values=["自動選擇", "獨立-1", "獨立-2", "獨立-3"]
        )
        self.detection_instance_combo.pack(side=tk.LEFT, padx=(0, 5))

        # 怪物名稱
        ttk.Label(settings_frame, text="怪物:").pack(side=tk.LEFT)
        saved_monster_name = global_settings.get("monster_hp_detection_monster_name", "")
        self.monster_name_entry = ttk.Entry(settings_frame, width=12)
        self.monster_name_entry.insert(0, saved_monster_name)
        self.monster_name_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        # 觸發血量
        ttk.Label(settings_frame, text="觸發血量:").pack(side=tk.LEFT)
        saved_threshold = global_settings.get("monster_hp_detection_threshold", "10000")
        self.hp_threshold_entry = ttk.Entry(settings_frame, width=12)
        self.hp_threshold_entry.insert(0, saved_threshold)
        self.hp_threshold_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        # 血量顯示
        self.monster_hp_label = ttk.Label(
            settings_frame, 
            text="--/--",
            font=("Microsoft JhengHei UI", 12, "bold"),
            foreground="#666666"
        )
        self.monster_hp_label.pack(side=tk.LEFT)

        # ==================== 按鈕控制區域 (第二行) ====================
        buttons_frame = ttk.Frame(global_control_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=2)

        # 全域定時指定目標按鈕
        self.global_timed_target_button = tk.Button(
            buttons_frame,
            text="全部啟動定時指定目標",
            command=self.toggle_all_timed_specify_target,
            font=("Microsoft JhengHei UI", 10, "bold"),
            bg="#959595",
            height=1
        )
        self.global_timed_target_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        
        # 偵測啟動按鈕
        self.monster_hp_detection_button = tk.Button(
            buttons_frame,
            text="偵測啟動",
            command=self.toggle_monster_hp_detection,
            font=("Microsoft JhengHei UI", 10, "bold"),
            bg="#4CAF50",
            fg="white",
            height=1
        )
        self.monster_hp_detection_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        
        # ==================== ADB 工具按鈕區域 (第三行) ====================
        adb_buttons_frame = ttk.Frame(global_control_frame)
        adb_buttons_frame.pack(fill=tk.X, padx=5, pady=2)
        
        # ADB 指令按鈕
        self.adb_commands_button = tk.Button(
            adb_buttons_frame,
            text="ADB指令",
            command=self.open_adb_commands_dialog,
            font=("Microsoft JhengHei UI", 10, "bold"),
            bg="#2196F3",
            fg="white",
            height=1
        )
        self.adb_commands_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 動畫與狀態變數

        self._global_button_animating = False
        self._global_button_blink_state = False
        self._is_hp_detecting = False
        self._hp_detection_thread = None
        
        # Create 3 independent control columns
        for i in range(1, 4):
            name = f"獨立-{i}"
            
            # Initialize instance data (minimal set for connection and specify target)
            self.instances[name] = {
                "config": {
                    "timed_target_interval": "1",
                    "timed_skill_interval": "1",
                    "skill_id": "",
                    "barrier_interval": "10",
                }, 
                "session": None, "is_monitoring": False,
                "monitor_thread": None, "script_api": None, "ui": {},
                "is_seq_moving": False, "seq_move_thread": None,
                "is_patrolling": False, "patrol_thread": None,
                "is_barrier_running": False, "barrier_thread": None,
                "is_monster_detecting": False, "monster_detect_thread": None,
                "last_notification_time": 0,
                "last_notified_target": None,
                "is_timed_targeting": False, 
                "timed_target_thread": None,
                "is_timed_skilling": False, 
                "timed_skill_thread": None,
                "is_auto_barrier_running": False,
                "auto_barrier_thread": None,
                "is_general_afk_running": False,
                "general_afk_buff_thread": None,
                "general_afk_attack_thread": None,
                "buff_last_cast": {},
                "attack_last_cast": {},
            }
            ui = self.instances[name]["ui"]
            
            # Vars for Specify Target
            ui["monitor_target_var"] = tk.BooleanVar()
            ui["monitor_pos_var"] = tk.BooleanVar()
            ui["monitor_target_teleport_var"] = tk.BooleanVar()
            ui["telegram_notify_var"] = tk.BooleanVar()
            ui["use_forgotten_island_scroll_var"] = tk.BooleanVar()
            ui["auto_attack_pickup_var"] = tk.BooleanVar()
            ui["specify_target_priority_var"] = tk.BooleanVar()

            ui["specify_target_selected_group_name_var"] = tk.StringVar(value="目標組 1")
            ui["specify_target_selected_group_index"] = tk.IntVar(value=0)
            ui["specify_target_groups"] = [{"name": f"目標組 {j+1}", "targets": ""} for j in range(5)]

            # Copy target groups from existing emulator config if available
            if hasattr(self, 'config') and "emulators" in self.config:
                 if i-1 < len(self.config["emulators"]):
                     emu_conf = self.config["emulators"][i-1]
                     loaded_groups = emu_conf.get("specify_target_groups", [])
                     if loaded_groups:
                        # Deep copy to avoid reference issues
                        ui["specify_target_groups"] = [dict(g) for g in loaded_groups]
                        # Ensure at least 5 groups
                        while len(ui["specify_target_groups"]) < 5:
                             j = len(ui["specify_target_groups"])
                             ui["specify_target_groups"].append({"name": f"目標組 {j+1}", "targets": ""})
                     
                     selected_idx = emu_conf.get("specify_target_selected_group_index", 0)
                     if 0 <= selected_idx < len(ui["specify_target_groups"]):
                         ui["specify_target_selected_group_index"].set(selected_idx)
                         ui["specify_target_selected_group_name_var"].set(ui["specify_target_groups"][selected_idx]["name"])
                     
                     # Load checkbox states
                     ui["auto_attack_pickup_var"].set(emu_conf.get("auto_attack_pickup_on", False))
                     ui["specify_target_priority_var"].set(emu_conf.get("specify_target_priority_on", False))
                     
                     # Load interval setting to instance config
                     self.instances[name]["config"]["timed_target_interval"] = emu_conf.get("timed_target_interval", "1")
                     self.instances[name]["config"]["barrier_interval"] = emu_conf.get("barrier_interval", "10")

            # Column Frame (Compact padding)
            col_frame = ttk.LabelFrame(tab_frame, text=f"控制區塊 {i}", padding="2")
            col_frame.grid(row=1, column=i-1, sticky="nsew", padx=2, pady=2)  # 改為 row=1,因為 row=0 是全域控制
            
            # Connection Part
            conn_frame = ttk.Frame(col_frame)
            conn_frame.pack(fill=tk.X, pady=1)
            ttk.Label(conn_frame, text="Port:").pack(side=tk.LEFT)
            ui["port_entry"] = ttk.Entry(conn_frame, width=8)
            ui["port_entry"].pack(side=tk.LEFT, padx=2)
            
            # Pre-fill port from existing emulator config if available
            if hasattr(self, 'config') and "emulators" in self.config:
                 if i-1 < len(self.config["emulators"]):
                     default_port = self.config["emulators"][i-1].get("port", "")
                     ui["port_entry"].insert(0, default_port)

            ui["connect_button"] = ttk.Button(conn_frame, text="連線", command=lambda n=name: self.connect_thread(n), style='Taller.TButton')
            ui["connect_button"].pack(side=tk.LEFT, padx=2)
            
            # Create hidden entries required by establish_connection
            # Fetch defaults from global config if available
            global_config = getattr(self, 'config', {})
            
            ui["c0391_class_name_entry"] = ttk.Entry(tab_frame)
            ui["c0391_class_name_entry"].insert(0, global_config.get("c0391_class_name", "ቌ.ᣇ.ᶬ.ಞ.㚽.Ố"))
            
            ui["socket_utils_method_entry"] = ttk.Entry(tab_frame)
            ui["socket_utils_method_entry"].insert(0, global_config.get("socket_utils_method", "ᶬ"))
            
            ui["moveto_classname_entry"] = ttk.Entry(tab_frame)
            ui["moveto_classname_entry"].insert(0, global_config.get("moveto_classname", "䄼"))
            
            ui["use_item_method_name_entry"] = ttk.Entry(tab_frame)
            ui["use_item_method_name_entry"].insert(0, global_config.get("use_item_method_name", "䇪"))
            
            ui["auto_method_entry"] = ttk.Entry(tab_frame)
            ui["auto_method_entry"].insert(0, global_config.get("auto_method", ""))
            
            ui["skill_use_method_name_entry"] = ttk.Entry(tab_frame)
            ui["skill_use_method_name_entry"].insert(0, global_config.get("skill_use_method_name", ""))
            
            ui["target_method_name_entry"] = ttk.Entry(tab_frame)
            ui["target_method_name_entry"].insert(0, global_config.get("target_method_name", ""))
            
            ui["attack_pickup_method_name_entry"] = ttk.Entry(tab_frame)
            ui["attack_pickup_method_name_entry"].insert(0, global_config.get("attack_pickup_method_name", ""))
            
            # Add missing UI entries required by establish_connection
            ui["adb_path_entry"] = ttk.Entry(tab_frame)
            # Load from existing emulator config if available
            if hasattr(self, 'config') and "emulators" in self.config:
                if i-1 < len(self.config["emulators"]):
                    default_adb_path = self.config["emulators"][i-1].get("adb_path", "C:\\LDPlayer\\LDPlayer9\\adb.exe")
                    ui["adb_path_entry"].insert(0, default_adb_path)
                else:
                    ui["adb_path_entry"].insert(0, "C:\\LDPlayer\\LDPlayer9\\adb.exe")
            else:
                ui["adb_path_entry"].insert(0, "C:\\LDPlayer\\LDPlayer9\\adb.exe")
            
            ui["device_serial_entry"] = ttk.Entry(tab_frame)
            # Load from existing emulator config if available
            if hasattr(self, 'config') and "emulators" in self.config:
                if i-1 < len(self.config["emulators"]):
                    default_device = self.config["emulators"][i-1].get("device_serial", "emulator-5554")
                    ui["device_serial_entry"].insert(0, default_device)
                else:
                    ui["device_serial_entry"].insert(0, "emulator-5554")
            else:
                ui["device_serial_entry"].insert(0, "emulator-5554")
            
            ui["forward_port_entry"] = ttk.Entry(tab_frame)
            # Load from existing emulator config if available
            if hasattr(self, 'config') and "emulators" in self.config:
                if i-1 < len(self.config["emulators"]):
                    default_forward_port = self.config["emulators"][i-1].get("forward_port", "27043")
                    ui["forward_port_entry"].insert(0, default_forward_port)
                else:
                    ui["forward_port_entry"].insert(0, "27043")
            else:
                ui["forward_port_entry"].insert(0, "27043")
            
            # Also need skill_id_entry for create_specify_target_ui to work (it loads from config but might need entry)
            ui["skill_id_entry"] = ttk.Entry(tab_frame) # Hidden
            
            # Hidden text widget for storing current targets (required by specify_closest_target_thread)
            ui["specify_target_current_targets_text"] = scrolledtext.ScrolledText(tab_frame, height=3, width=20)
            
            # Initialize current targets text based on default group
            ui["specify_target_current_targets_text"].insert("1.0", ui["specify_target_groups"][0]["targets"])
            ui["specify_target_current_targets_text"].config(state='disabled')

            # Create Specify Target UI (Compact)
            self.create_specify_target_ui(col_frame, name, padding="2")
            
            # --- Auto Barrier Frame ---
            barrier_frame = ttk.LabelFrame(col_frame, text="自動魔法屏障", padding="2")
            barrier_frame.pack(side=tk.TOP, fill=tk.X, pady=(5,0))
            barrier_frame.grid_columnconfigure(1, weight=1)
            
            ttk.Label(barrier_frame, text="間隔(秒):").grid(row=0, column=0, sticky="w", padx=2, pady=2)
            ui["barrier_interval_entry"] = ttk.Entry(barrier_frame, width=10)
            ui["barrier_interval_entry"].grid(row=0, column=1, sticky="ew", padx=2, pady=2)
            
            ui["barrier_toggle_button"] = ttk.Button(barrier_frame, text="開始施放", command=lambda n=name: self.toggle_auto_barrier(n), style='Taller.TButton')
            ui["barrier_toggle_button"].grid(row=1, column=0, columnspan=2, pady=2, sticky="ew")
            
            # Pre-fill barrier interval from existing emulator config if available
            if hasattr(self, 'config') and "emulators" in self.config:
                if i-1 < len(self.config["emulators"]):
                    default_barrier_interval = self.config["emulators"][i-1].get("barrier_interval", "10")
                    ui["barrier_interval_entry"].insert(0, default_barrier_interval)
            
            # Set initial button state (disabled until connected)
            if self.instances[name].get("session") and not self.instances[name]["session"].is_detached:
                ui["barrier_toggle_button"].config(state='normal')
            else:
                ui["barrier_toggle_button"].config(state='disabled')

    def create_specify_target_ui(self, parent, name, padding="10"):
        instance = self.instances[name]
        ui = instance["ui"]

        # --- Specify Target Frame ---
        target_frame = ttk.LabelFrame(parent, text="指定目標", padding=padding)
        target_frame.pack(side=tk.TOP, fill=tk.X, pady=(5,0))
        target_frame.grid_columnconfigure(0, weight=1)

        group_selection_frame = ttk.Frame(target_frame)
        group_selection_frame.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(group_selection_frame, text="目標組:").pack(side=tk.LEFT)
        ui["specify_target_group_combobox"] = ttk.Combobox(group_selection_frame, textvariable=ui["specify_target_selected_group_name_var"], state="readonly", width=12)
        ui["specify_target_group_combobox"].pack(side=tk.LEFT, padx=(5,0))
        ui["specify_target_group_combobox"].bind("<<ComboboxSelected>>", lambda event, n=name: self.on_specify_target_group_selected(n))

        checkbox_frame = ttk.Frame(target_frame)
        checkbox_frame.pack(fill=tk.X, pady=(0, 2))
        ttk.Checkbutton(checkbox_frame, text="攻擊/撿取", variable=ui["auto_attack_pickup_var"]).pack(side=tk.LEFT, padx=(0,5))
        
        priority_frame = ttk.Frame(target_frame)
        priority_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Checkbutton(priority_frame, text="啟用列表順序優先級", variable=ui["specify_target_priority_var"]).pack(side=tk.LEFT)

        specify_target_buttons_frame = ttk.Frame(target_frame)
        specify_target_buttons_frame.pack(fill='x', expand=True, pady=(2, 5))

        ui["edit_specify_targets_button"] = ttk.Button(specify_target_buttons_frame, text="目標列表", command=lambda n=name: self.open_specify_target_dialog(n), style='Taller.TButton')
        ui["edit_specify_targets_button"].pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 2))

        ui["specify_target_button"] = ttk.Button(specify_target_buttons_frame, text="最近目標", command=lambda n=name: self.specify_closest_target_thread(n), style='Taller.TButton')
        ui["specify_target_button"].pack(side=tk.LEFT, fill='x', expand=True, padx=(2, 0))

        timed_target_frame = ttk.Frame(target_frame)
        timed_target_frame.pack(fill=tk.X, pady=(5, 0), expand=True)
        
        ui["timed_target_button"] = ttk.Button(timed_target_frame, text="定時指定目標", command=lambda n=name: self.toggle_timed_specify_target(n), style='Taller.TButton')
        ui["timed_target_button"].pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 2))

        ttk.Label(timed_target_frame, text="間隔(秒):").pack(side=tk.LEFT, padx=(5, 2))
        ui["timed_target_interval_entry"] = ttk.Entry(timed_target_frame, width=5)
        ui["timed_target_interval_entry"].pack(side=tk.LEFT)

        # Load config and set states
        emu_config = self.instances[name]["config"]
        ui["timed_target_interval_entry"].insert(0, emu_config.get("timed_target_interval", "1"))
        
        new_combobox_values = [group["name"] for group in ui["specify_target_groups"]]
        ui["specify_target_group_combobox"]['values'] = new_combobox_values
        selected_group_index = ui["specify_target_selected_group_index"].get()
        ui["specify_target_group_combobox"].set(ui["specify_target_groups"][selected_group_index]["name"])

        if instance.get("session") and not instance["session"].is_detached:
            ui["edit_specify_targets_button"].config(state='normal')
            ui["specify_target_button"].config(state='normal')
            ui["timed_target_button"].config(state='normal')
        else:
            ui["edit_specify_targets_button"].config(state='disabled')
            ui["specify_target_button"].config(state='disabled')
            ui["timed_target_button"].config(state='disabled')

    def open_advanced_features_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 進階功能")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        # 延後設定視窗位置,等UI元件創建完成後再設定

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)

        # --- Skill Use Frame ---
        skill_frame = ttk.LabelFrame(main_frame, text="技能測試", padding="10")
        skill_frame.pack(side=tk.TOP, fill=tk.X, pady=(5,0))
        skill_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(skill_frame, text="技能 ID :").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ui["skill_id_entry"] = ttk.Entry(skill_frame, width=10)
        ui["skill_id_entry"].grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        
        # Target Key row
        ttk.Label(skill_frame, text="目標 Key:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        target_key_frame = ttk.Frame(skill_frame)
        target_key_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        
        ui["target_key_entry"] = ttk.Entry(target_key_frame, width=15)
        ui["target_key_entry"].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ui["target_key_entry"].insert(0, "0")
        
        ui["select_player_button"] = ttk.Button(target_key_frame, text="選擇玩家", command=lambda n=name: self.select_nearby_player_thread(n), style='Taller.TButton')
        ui["select_player_button"].pack(side=tk.LEFT)
        
        skill_button_frame = ttk.Frame(skill_frame)
        skill_button_frame.grid(row=2, column=0, columnspan=2, pady=5, sticky="ew")

        ui["select_skill_button"] = ttk.Button(skill_button_frame, text="選擇技能", command=lambda n=name: self.select_skill_thread(n, ui["skill_id_entry"], ui["select_skill_button"]), style='Taller.TButton')
        ui["select_skill_button"].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        ui["use_skill_button"] = ttk.Button(skill_button_frame, text="使用技能", command=lambda n=name: self.use_skill_thread(n), style='Taller.TButton')
        ui["use_skill_button"].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        timed_skill_frame = ttk.Frame(skill_frame)
        timed_skill_frame.grid(row=3, column=0, columnspan=2, pady=(5, 0), sticky="ew")
        
        ui["timed_skill_button"] = ttk.Button(timed_skill_frame, text="定時施法", command=lambda n=name: self.toggle_timed_skill(n), style='Taller.TButton')
        ui["timed_skill_button"].pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 2))

        ttk.Label(timed_skill_frame, text="間隔(秒):").pack(side=tk.LEFT, padx=(5, 2))
        ui["timed_skill_interval_entry"] = ttk.Entry(timed_skill_frame, width=5)
        ui["timed_skill_interval_entry"].pack(side=tk.LEFT)

        # Load config
        emu_config = self.instances[name]["config"]
        ui["skill_id_entry"].insert(0, emu_config.get("skill_id", ""))
        ui["timed_skill_interval_entry"].insert(0, emu_config.get("timed_skill_interval", "1"))

        if instance.get("session") and not instance["session"].is_detached:
            ui["select_skill_button"].config(state='normal')
            ui["select_player_button"].config(state='normal')
            ui["use_skill_button"].config(state='normal')
            ui["timed_skill_button"].config(state='normal')
        else:
            ui["select_skill_button"].config(state='disabled')
            ui["select_player_button"].config(state='disabled')
            ui["use_skill_button"].config(state='disabled')
            ui["timed_skill_button"].config(state='disabled')

        self.create_specify_target_ui(main_frame, name)

        def save_and_close_dialog():
            # Save settings to instance config before destroying widgets
            instance["config"]["timed_skill_interval"] = ui["timed_skill_interval_entry"].get()
            instance["config"]["timed_target_interval"] = ui["timed_target_interval_entry"].get()
            instance["config"]["skill_id"] = ui["skill_id_entry"].get()
            self.log_message(f"[{name}] 已儲存進階功能設定。")
            # Persist changes to config.json
            self.save_config()

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ok_button = ttk.Button(button_frame, text="儲存", command=save_and_close_dialog, style='Taller.TButton')
        ok_button.pack(side=tk.RIGHT)

        # 所有UI元件創建完成後,設定視窗位置並顯示
        self.root.update_idletasks()
        dialog_width = 300
        dialog_height = 390
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)

    def open_test_features_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        # Add state tracking to instance if not present
        if "is_priority_targeting" not in instance:
            instance["is_priority_targeting"] = False
            instance["priority_targeting_thread"] = None

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 自動聚怪設定")
        dialog.transient(self.root)
        dialog.resizable(True, True)
        # 延後設定視窗位置,等UI元件創建完成後再設定

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)

        # --- Settings Frame ---
        settings_frame = ttk.LabelFrame(main_frame, text="設定", padding="10")
        settings_frame.grid(row=0, column=0, sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="清怪數量 (上限):").grid(row=0, column=0, sticky="w", pady=2, padx=2)
        ui["priority_attacker_threshold_entry"] = ttk.Entry(settings_frame, width=10)
        ui["priority_attacker_threshold_entry"].grid(row=0, column=1, sticky="w", pady=2, padx=2)
        ui["priority_attacker_threshold_entry"].insert(0, instance["config"].get("priority_attacker_threshold", "3"))

        ttk.Label(settings_frame, text="聚怪數量 (下限):").grid(row=1, column=0, sticky="w", pady=2, padx=2)
        ui["priority_lower_threshold_entry"] = ttk.Entry(settings_frame, width=10)
        ui["priority_lower_threshold_entry"].grid(row=1, column=1, sticky="w", pady=2, padx=2)
        ui["priority_lower_threshold_entry"].insert(0, instance["config"].get("priority_lower_threshold", "1"))

        # --- New Safety Settings (Moved to Advanced) ---
        # ---------------------------

        ttk.Label(settings_frame, text="聚怪使用技能ID:").grid(row=4, column=0, sticky="w", pady=2, padx=2)
        
        skill_input_frame = ttk.Frame(settings_frame)
        skill_input_frame.grid(row=4, column=1, sticky="w", pady=2, padx=2)
        # Removed skill_input_frame.grid_columnconfigure(0, weight=1)

        ui["priority_skill_id_entry"] = ttk.Entry(skill_input_frame, width=10)
        ui["priority_skill_id_entry"].grid(row=0, column=0)
        ui["priority_skill_id_entry"].insert(0, instance["config"].get("priority_skill_id", ""))
        
        ttk.Label(skill_input_frame, text="(留空=普攻)", font=("Arial", 8), foreground="gray").grid(row=0, column=2, padx=(5,0))
        
        ui["priority_select_skill_button"] = ttk.Button(skill_input_frame, text="選擇", command=lambda n=name: self.select_skill_thread(n, ui["priority_skill_id_entry"], ui["priority_select_skill_button"]), style='Taller.TButton', width=5)
        ui["priority_select_skill_button"].grid(row=0, column=1, padx=(5,0))
        
        ttk.Label(settings_frame, text="檢查間隔(秒):").grid(row=5, column=0, sticky="w", pady=2, padx=2)
        ui["priority_interval_entry"] = ttk.Entry(settings_frame, width=10)
        ui["priority_interval_entry"].grid(row=5, column=1, sticky="w", pady=2, padx=2)
        ui["priority_interval_entry"].insert(0, instance["config"].get("priority_interval", "0.5"))

        # Moved to Advanced
        # ttk.Label(settings_frame, text="最小引誘距離:").grid(row=6, column=0, sticky="w", pady=2, padx=2)
        # ui["priority_min_lure_distance_entry"] = ttk.Entry(settings_frame, width=10)
        # ui["priority_min_lure_distance_entry"].grid(row=6, column=1, sticky="w", pady=2, padx=2)
        # ui["priority_min_lure_distance_entry"].insert(0, instance["config"].get("priority_min_lure_distance", "5"))

        # ttk.Label(settings_frame, text="成功引誘忽略(秒):").grid(row=7, column=0, sticky="w", pady=2, padx=2)
        # ui["priority_lure_ignore_time_entry"] = ttk.Entry(settings_frame, width=10)
        # ui["priority_lure_ignore_time_entry"].grid(row=7, column=1, sticky="w", pady=2, padx=2)
        # ui["priority_lure_ignore_time_entry"].insert(0, instance["config"].get("priority_lure_ignore_time", "2"))

        ttk.Label(settings_frame, text="引誘範圍:").grid(row=8, column=0, sticky="w", pady=2, padx=2)
        ui["priority_luring_range_entry"] = ttk.Entry(settings_frame, width=10)
        ui["priority_luring_range_entry"].grid(row=8, column=1, sticky="w", pady=2, padx=2)
        ui["priority_luring_range_entry"].insert(0, instance["config"].get("priority_luring_range", "50"))

        # --- Low Density Teleport ---
        low_density_frame = ttk.LabelFrame(main_frame, text="低密度順移設定", padding="5")
        low_density_frame.grid(row=1, column=0, sticky="ew", pady=5)
        low_density_frame.grid_columnconfigure(1, weight=1)

        ui["priority_low_density_teleport_var"] = tk.BooleanVar(value=instance["config"].get("priority_low_density_teleport_on", False))
        ttk.Checkbutton(low_density_frame, text="啟用低密度順移", variable=ui["priority_low_density_teleport_var"]).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(low_density_frame, text="順移門檻 (隻):").grid(row=1, column=0, sticky="w", pady=2, padx=2)
        ui["priority_low_density_threshold_entry"] = ttk.Entry(low_density_frame, width=10)
        ui["priority_low_density_threshold_entry"].grid(row=1, column=1, sticky="w", pady=2, padx=2)
        ui["priority_low_density_threshold_entry"].insert(0, instance["config"].get("priority_low_density_threshold", "3"))

        ttk.Label(low_density_frame, text="偵測範圍:").grid(row=2, column=0, sticky="w", pady=2, padx=2)
        ui["priority_low_density_range_entry"] = ttk.Entry(low_density_frame, width=10)
        ui["priority_low_density_range_entry"].grid(row=2, column=1, sticky="w", pady=2, padx=2)
        ui["priority_low_density_range_entry"].insert(0, instance["config"].get("priority_low_density_range", "30"))

        ttk.Label(low_density_frame, text="順移冷卻 (秒):").grid(row=3, column=0, sticky="w", pady=2, padx=2)
        ui["priority_low_density_cooldown_entry"] = ttk.Entry(low_density_frame, width=10)
        ui["priority_low_density_cooldown_entry"].grid(row=3, column=1, sticky="w", pady=2, padx=2)
        ui["priority_low_density_cooldown_entry"].insert(0, instance["config"].get("priority_low_density_cooldown", "5.0"))

        # --- Advanced Settings Button ---
        def open_advanced_settings():
            adv_dialog = tk.Toplevel(dialog)
            adv_dialog.title(f"[{name}] 進階聚怪設定")
            adv_dialog.transient(dialog)
            adv_dialog.resizable(True, True)
            
            adv_frame = ttk.Frame(adv_dialog, padding="10")
            adv_frame.pack(expand=True, fill=tk.BOTH)
            adv_frame.grid_columnconfigure(1, weight=1)
            adv_frame.grid_rowconfigure(2, weight=1) # Listboxes expand

            # --- Pickup Range ---
            ttk.Label(adv_frame, text="優先撿取範圍:").grid(row=0, column=0, sticky="w", pady=2, padx=2)
            priority_pickup_range_entry = ttk.Entry(adv_frame, width=10)
            priority_pickup_range_entry.grid(row=0, column=1, sticky="w", pady=2, padx=2)
            priority_pickup_range_entry.insert(0, instance["config"].get("priority_pickup_range", "200"))
            ttk.Label(adv_frame, text="(0=不限)").grid(row=0, column=2, sticky="w", padx=2)

            # --- Priority Pickup List ---
            ttk.Label(adv_frame, text="優先撿物列表:").grid(row=1, column=0, sticky="nw", pady=2, padx=2)
            pickup_frame = ttk.Frame(adv_frame)
            pickup_frame.grid(row=1, column=1, columnspan=2, sticky="ew", pady=2, padx=2)
            priority_pickup_entry = tk.Text(pickup_frame, height=13, width=30)
            priority_pickup_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            pickup_scroll = ttk.Scrollbar(pickup_frame, orient="vertical", command=priority_pickup_entry.yview)
            pickup_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            priority_pickup_entry.config(yscrollcommand=pickup_scroll.set)
            
            saved_pickup = instance["config"].get("priority_pickup_list", "")
            formatted_pickup = "\n".join([x.strip() for x in saved_pickup.split(',') if x.strip()])
            priority_pickup_entry.insert("1.0", formatted_pickup)

            # --- Blacklist ---
            ttk.Label(adv_frame, text="不攻擊怪物列表:").grid(row=2, column=0, sticky="nw", pady=2, padx=2)
            blacklist_frame = ttk.Frame(adv_frame)
            blacklist_frame.grid(row=2, column=1, columnspan=2, sticky="ew", pady=2, padx=2)
            priority_monster_blacklist_entry = tk.Text(blacklist_frame, height=13, width=30)
            priority_monster_blacklist_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            blacklist_scroll = ttk.Scrollbar(blacklist_frame, orient="vertical", command=priority_monster_blacklist_entry.yview)
            blacklist_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            priority_monster_blacklist_entry.config(yscrollcommand=blacklist_scroll.set)
            
            saved_blacklist = instance["config"].get("priority_monster_blacklist", "史萊姆,葛林")
            formatted_blacklist = "\n".join([x.strip() for x in saved_blacklist.split(',') if x.strip()])
            priority_monster_blacklist_entry.insert("1.0", formatted_blacklist)

            priority_monster_blacklist_entry.insert("1.0", formatted_blacklist)

            # --- Safety Settings Removed from Advanced ---

            def save_advanced_settings():
                instance["config"]["priority_pickup_range"] = priority_pickup_range_entry.get()
                instance["config"]["priority_pickup_list"] = priority_pickup_entry.get("1.0", tk.END).replace('\n', ',').strip()
                instance["config"]["priority_monster_blacklist"] = priority_monster_blacklist_entry.get("1.0", tk.END).replace('\n', ',').strip()
                
                # Safety settings moved to separate dialog
                
                self.save_config()
                self.log_message(f"[{name}] 已儲存進階聚怪設定。")
                adv_dialog.destroy()

            save_btn = ttk.Button(adv_frame, text="儲存並關閉", command=save_advanced_settings, style='Taller.TButton')
            save_btn.grid(row=4, column=0, columnspan=3, pady=5)

            # Center dialog
            self.root.update_idletasks()
            d_width = 400
            d_height = 430 # Reverted height
            m_x = self.root.winfo_x()
            m_y = self.root.winfo_y()
            m_w = self.root.winfo_width()
            m_h = self.root.winfo_height()
            c_x = m_x + (m_w - d_width) // 2
            c_y = m_y + (m_h - d_height) // 2
            adv_dialog.geometry(f"{d_width}x{d_height}+{c_x}+{c_y}")



        ui["priority_density_detection_var"] = tk.BooleanVar()
        ttk.Checkbutton(settings_frame, text="啟用怪物密度偵測", variable=ui["priority_density_detection_var"]).grid(row=10, column=0, sticky="w", pady=2, padx=2)
        ui["priority_density_detection_var"].set(instance["config"].get("priority_density_detection", False))

        density_radius_frame = ttk.Frame(settings_frame)
        density_radius_frame.grid(row=10, column=1, sticky="w", pady=2, padx=2)
        ttk.Label(density_radius_frame, text="半徑:       ").pack(side=tk.LEFT)
        ui["priority_cluster_radius_entry"] = ttk.Entry(density_radius_frame, width=5)
        ui["priority_cluster_radius_entry"].pack(side=tk.LEFT, padx=5)
        ui["priority_cluster_radius_entry"].insert(0, instance["config"].get("priority_cluster_radius", "15"))

        # --- Safety Settings Button ---
        def open_safety_settings():
            safety_dialog = tk.Toplevel(dialog)
            safety_dialog.title(f"[{name}] 安全與微調設定")
            safety_dialog.transient(dialog)
            safety_dialog.resizable(True, True)
            
            safety_frame = ttk.Frame(safety_dialog, padding="10")
            safety_frame.pack(expand=True, fill=tk.BOTH)
            safety_frame.grid_columnconfigure(1, weight=1)

            # Safety Distance
            ttk.Label(safety_frame, text="近身安全距離:").grid(row=0, column=0, sticky="w", pady=2, padx=2)
            priority_safety_distance_entry = ttk.Entry(safety_frame, width=10)
            priority_safety_distance_entry.grid(row=0, column=1, sticky="w", pady=2, padx=2)
            priority_safety_distance_entry.insert(0, instance["config"].get("priority_safety_distance", "2"))

            # Safety Count
            ttk.Label(safety_frame, text="近身危險數量:").grid(row=1, column=0, sticky="w", pady=2, padx=2)
            priority_safety_count_entry = ttk.Entry(safety_frame, width=10)
            priority_safety_count_entry.grid(row=1, column=1, sticky="w", pady=2, padx=2)
            priority_safety_count_entry.insert(0, instance["config"].get("priority_safety_count", "2"))

            # Min Lure Distance
            ttk.Label(safety_frame, text="最小引誘距離:").grid(row=2, column=0, sticky="w", pady=2, padx=2)
            priority_min_lure_distance_entry = ttk.Entry(safety_frame, width=10)
            priority_min_lure_distance_entry.grid(row=2, column=1, sticky="w", pady=2, padx=2)
            priority_min_lure_distance_entry.insert(0, instance["config"].get("priority_min_lure_distance", "5"))

            # Lure Ignore Time
            ttk.Label(safety_frame, text="成功引誘忽略(秒):").grid(row=3, column=0, sticky="w", pady=2, padx=2)
            priority_lure_ignore_time_entry = ttk.Entry(safety_frame, width=10)
            priority_lure_ignore_time_entry.grid(row=3, column=1, sticky="w", pady=2, padx=2)
            priority_lure_ignore_time_entry.insert(0, instance["config"].get("priority_lure_ignore_time", "2"))

            # Stuck Teleport
            stuck_frame = ttk.Frame(safety_frame)
            stuck_frame.grid(row=4, column=0, columnspan=2, sticky="w", pady=2, padx=2)
            
            priority_stuck_teleport_var = tk.BooleanVar()
            ttk.Checkbutton(stuck_frame, text="啟用卡點順移", variable=priority_stuck_teleport_var).pack(side=tk.LEFT)
            priority_stuck_teleport_var.set(instance["config"].get("priority_stuck_teleport", False))
            
            priority_stuck_time_entry = ttk.Entry(stuck_frame, width=5)
            priority_stuck_time_entry.pack(side=tk.LEFT, padx=5)
            priority_stuck_time_entry.insert(0, instance["config"].get("priority_stuck_time", "5"))
            
            ttk.Label(stuck_frame, text="秒").pack(side=tk.LEFT)

            def save_safety_settings():
                instance["config"]["priority_safety_distance"] = priority_safety_distance_entry.get()
                instance["config"]["priority_safety_count"] = priority_safety_count_entry.get()
                instance["config"]["priority_min_lure_distance"] = priority_min_lure_distance_entry.get()
                instance["config"]["priority_lure_ignore_time"] = priority_lure_ignore_time_entry.get()
                instance["config"]["priority_stuck_teleport"] = priority_stuck_teleport_var.get()
                instance["config"]["priority_stuck_time"] = priority_stuck_time_entry.get()
                self.save_config()
                self.log_message(f"[{name}] 已儲存安全設定。")
                safety_dialog.destroy()

            save_btn = ttk.Button(safety_frame, text="儲存並關閉", command=save_safety_settings, style='Taller.TButton')
            save_btn.grid(row=5, column=0, columnspan=2, pady=5)

            # Center dialog
            self.root.update_idletasks()
            d_width = 200
            d_height = 180
            m_x = self.root.winfo_x()
            m_y = self.root.winfo_y()
            m_w = self.root.winfo_width()
            m_h = self.root.winfo_height()
            c_x = m_x + (m_w - d_width) // 2
            c_y = m_y + (m_h - d_height) // 2
            safety_dialog.geometry(f"{d_width}x{d_height}+{c_x}+{c_y}")

        # --- Density Detection Settings ---
        ui["priority_density_switch_on_hp_loss_var"] = tk.BooleanVar()
        ttk.Checkbutton(settings_frame, text="密度模式血量切換", variable=ui["priority_density_switch_on_hp_loss_var"]).grid(row=11, column=0, sticky="w", pady=2, padx=2)
        ui["priority_density_switch_on_hp_loss_var"].set(instance["config"].get("priority_density_switch_on_hp_loss", False))

        density_lock_frame = ttk.Frame(settings_frame)
        density_lock_frame.grid(row=11, column=1, sticky="w", pady=2, padx=2)
        ttk.Label(density_lock_frame, text="鎖定(秒):").pack(side=tk.LEFT)
        ui["priority_density_lock_duration_entry"] = ttk.Entry(density_lock_frame, width=5)
        ui["priority_density_lock_duration_entry"].pack(side=tk.LEFT, padx=5)
        ui["priority_density_lock_duration_entry"].insert(0, instance["config"].get("priority_density_lock_duration", "5.0"))
        # --- Advanced & Safety Buttons (Moved to Settings Frame) ---
        adv_safety_frame = ttk.Frame(settings_frame)
        adv_safety_frame.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(5, 2))
        
        advanced_button = ttk.Button(adv_safety_frame, text="進階設定", command=open_advanced_settings, style='Taller.TButton')
        advanced_button.pack(side=tk.LEFT, padx=(0, 5), expand=True, fill=tk.X)

        safety_button = ttk.Button(adv_safety_frame, text="安全設定", command=open_safety_settings, style='Taller.TButton')
        safety_button.pack(side=tk.LEFT, expand=True, fill=tk.X)

        
        # --- Status Frame (即時狀態顯示) ---
        status_frame = ttk.LabelFrame(main_frame, text="即時狀態", padding="10")
        status_frame.grid(row=2, column=0, sticky="ew", pady=(5,0))
        status_frame.grid_columnconfigure(1, weight=1)

        # 當前模式
        ttk.Label(status_frame, text="當前模式:").grid(row=0, column=0, sticky="w", pady=2)
        ui["priority_status_mode_label"] = ttk.Label(status_frame, text="未啟動", foreground="gray")
        ui["priority_status_mode_label"].grid(row=0, column=1, sticky="w", pady=2)

        # 聚怪進度
        ttk.Label(status_frame, text="聚怪進度:").grid(row=1, column=0, sticky="w", pady=2)
        progress_frame = ttk.Frame(status_frame)
        progress_frame.grid(row=1, column=1, sticky="ew", pady=2)
        
        # 進度條
        ui["priority_progress_bar"] = ttk.Progressbar(progress_frame, mode='determinate', length=200)
        ui["priority_progress_bar"].pack(fill=tk.X, expand=True)
        
        # 將數量標籤疊加在進度條上方 (使用 place 佈局)
        ui["priority_progress_label"] = ttk.Label(progress_frame, text="0/0", anchor="center")
        ui["priority_progress_label"].place(relx=0.5, rely=0.5, anchor="center")

        # 範圍內怪物
        ttk.Label(status_frame, text="📍 範圍內怪物:").grid(row=2, column=0, sticky="w", pady=2)
        ui["priority_total_monsters_label"] = ttk.Label(status_frame, text="0 隻")
        ui["priority_total_monsters_label"].grid(row=2, column=1, sticky="w", pady=2)

        # 可引誘目標
        ttk.Label(status_frame, text="✓ 可引誘:").grid(row=3, column=0, sticky="w", pady=2)
        ui["priority_valid_targets_label"] = ttk.Label(status_frame, text="0 隻")
        ui["priority_valid_targets_label"].grid(row=3, column=1, sticky="w", pady=2)

        # 黑名單怪物
        ttk.Label(status_frame, text="✗ 黑名單:").grid(row=4, column=0, sticky="w", pady=2)
        ui["priority_blacklist_count_label"] = ttk.Label(status_frame, text="0 隻")
        ui["priority_blacklist_count_label"].grid(row=4, column=1, sticky="w", pady=2)

        # 等待中目標
        ttk.Label(status_frame, text="⏱ 等待變紅:").grid(row=5, column=0, sticky="w", pady=2)
        ui["priority_pending_label"] = ttk.Label(status_frame, text="無")
        ui["priority_pending_label"].grid(row=5, column=1, sticky="w", pady=2)
        
        def close_dialog():
            # Save settings to config
            instance["config"]["priority_attacker_threshold"] = ui["priority_attacker_threshold_entry"].get()
            instance["config"]["priority_lower_threshold"] = ui["priority_lower_threshold_entry"].get()
            instance["config"]["priority_skill_id"] = ui["priority_skill_id_entry"].get()
            instance["config"]["priority_interval"] = ui["priority_interval_entry"].get()

            instance["config"]["priority_luring_range"] = ui["priority_luring_range_entry"].get()
            # Moved to Advanced:
            # instance["config"]["priority_min_lure_distance"] = ui["priority_min_lure_distance_entry"].get()
            # instance["config"]["priority_lure_ignore_time"] = ui["priority_lure_ignore_time_entry"].get()
            
            # Lists are now saved in the advanced dialog
            instance["config"]["priority_density_detection"] = ui["priority_density_detection_var"].get()
            instance["config"]["priority_cluster_radius"] = ui["priority_cluster_radius_entry"].get()
            
            # New Density Settings
            instance["config"]["priority_density_switch_on_hp_loss"] = ui["priority_density_switch_on_hp_loss_var"].get()
            instance["config"]["priority_density_lock_duration"] = ui["priority_density_lock_duration_entry"].get()

            # Moved to Advanced:
            # instance["config"]["priority_safety_distance"] = ui["priority_safety_distance_entry"].get()
            # instance["config"]["priority_safety_count"] = ui["priority_safety_count_entry"].get()
            # instance["config"]["priority_stuck_teleport"] = ui["priority_stuck_teleport_var"].get()
            # instance["config"]["priority_stuck_time"] = ui["priority_stuck_time_entry"].get()
            self.save_config() # Ensure settings are persisted to disk
            self.log_message(f"[{name}] 已儲存自動聚怪設定。")
        
        # --- Bottom Buttons ---
        # --- Bottom Buttons (Start & Save) ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, sticky="ew", pady=(10, 10))
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        
        ui["priority_targeting_button"] = ttk.Button(button_frame, text="開始", command=lambda n=name: self.toggle_priority_targeting(n), style='Taller.TButton')
        ui["priority_targeting_button"].grid(row=0, column=0, sticky="ew", padx=1)

        close_button = ttk.Button(button_frame, text="儲存", command=close_dialog, style='Taller.TButton')
        close_button.grid(row=0, column=1, sticky="ew", padx=1)
        
        # advanced_button & safety_button moved to settings_frame

        # Set initial state
        if instance.get("session") and not instance["session"].is_detached:
            ui["priority_targeting_button"].config(state='normal')
            ui["priority_select_skill_button"].config(state='normal')
        else:
            ui["priority_targeting_button"].config(state='disabled')
            ui["priority_select_skill_button"].config(state='disabled')
        
        if instance.get("is_priority_targeting", False):
            ui["priority_targeting_button"].config(text="停止")

        # 所有UI元件創建完成後,設定視窗位置並顯示
        self.root.update_idletasks()
        dialog_width = 320 # Increased width slightly
        dialog_height = 630  # Increased height for new settings
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)

    def toggle_priority_targeting(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        if instance["is_priority_targeting"]:
            instance["is_priority_targeting"] = False
            self.log_message(f"[{name}] --- 正在停止優先攻擊... ---")
            if ui["priority_targeting_button"].winfo_exists():
                ui["priority_targeting_button"].config(state='disabled', text="停止中...")
            return

        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        # 獲取並記錄起始地圖
        api = instance["script_api"]
        try:
            player_info_str = api.get_info(201)
            player_data = json.loads(player_info_str)
            info_dict = player_data.get('data', player_data)
            start_map_name = info_dict.get("mapName", "未知地圖")
        except Exception as e:
            start_map_name = f"讀取失敗: {e}"

        try:
            # Read from config (as some settings are now in Advanced dialog)
            # Note: UI entries in main dialog still exist for some, so we can read from them or config.
            # For consistency and to support the moved settings, we should prefer config or ensure UI updates config before this.
            # However, `toggle_priority_targeting` is called by the "Start" button in Main dialog.
            # The Main dialog entries are still valid for: Upper/Lower Threshold, Interval, Luring Range, Skill ID.
            # The Advanced dialog entries (Safety, Min Lure, etc.) are saved to config when Advanced dialog closes.
            # So we MUST read Safety/Min Lure/etc. from instance["config"].

            upper_threshold = int(ui["priority_attacker_threshold_entry"].get())
            lower_threshold = int(ui["priority_lower_threshold_entry"].get())
            interval = float(ui["priority_interval_entry"].get())
            luring_range = int(ui["priority_luring_range_entry"].get())
            skill_id_str = ui["priority_skill_id_entry"].get().strip()
            skill_id = int(skill_id_str) if skill_id_str.isdigit() else None
            
            # Read from Config (Moved to Advanced)
            safety_distance = int(instance["config"].get("priority_safety_distance", "2"))
            safety_count = int(instance["config"].get("priority_safety_count", "2"))
            min_lure_distance = float(instance["config"].get("priority_min_lure_distance", "5"))
            lure_ignore_time = float(instance["config"].get("priority_lure_ignore_time", "2"))
            use_stuck_teleport = instance["config"].get("priority_stuck_teleport", False)
            stuck_time = float(instance["config"].get("priority_stuck_time", "5"))

            # Read New Density Settings (In Main Dialog)
            use_density_detection = ui["priority_density_detection_var"].get()
            cluster_radius = int(ui["priority_cluster_radius_entry"].get())
            switch_on_hp_loss = ui["priority_density_switch_on_hp_loss_var"].get()
            lock_duration = float(ui["priority_density_lock_duration_entry"].get())

            # Read Low Density Teleport Settings
            low_density_teleport_on = ui["priority_low_density_teleport_var"].get()
            low_density_threshold = int(ui["priority_low_density_threshold_entry"].get())
            low_density_range = int(ui["priority_low_density_range_entry"].get())
            low_density_cooldown = float(ui["priority_low_density_cooldown_entry"].get())
            
            # Handle Text widgets for lists (split by newlines)
            # Read from config directly as the advanced dialog might be closed
            saved_pickup = instance["config"].get("priority_pickup_list", "")
            priority_pickup_list = [x.strip() for x in saved_pickup.split(',') if x.strip()]
            
            saved_blacklist = instance["config"].get("priority_monster_blacklist", "史萊姆,葛林")
            priority_monster_blacklist = [x.strip() for x in saved_blacklist.split(',') if x.strip()]
            
            use_density_detection = ui["priority_density_detection_var"].get()
            cluster_radius = int(ui["priority_cluster_radius_entry"].get())
            
            # FIX: Remove reading from UI variables that no longer exist in Main Dialog
            # use_stuck_teleport = ui["priority_stuck_teleport_var"].get()
            # stuck_time = float(ui["priority_stuck_time_entry"].get())
            # These are already read from config above:
            # use_stuck_teleport = instance["config"].get("priority_stuck_teleport", False)
            # stuck_time = float(instance["config"].get("priority_stuck_time", "5"))

            instance["config"]["priority_attacker_threshold"] = str(upper_threshold)
            instance["config"]["priority_lower_threshold"] = str(lower_threshold)
            instance["config"]["priority_interval"] = str(interval)
            instance["config"]["priority_luring_range"] = str(luring_range)
            instance["config"]["priority_skill_id"] = skill_id_str
            instance["config"]["priority_density_detection"] = use_density_detection
            instance["config"]["priority_cluster_radius"] = str(cluster_radius)
            instance["config"]["priority_density_switch_on_hp_loss"] = switch_on_hp_loss
            instance["config"]["priority_density_lock_duration"] = str(lock_duration)

            instance["config"]["priority_low_density_teleport_on"] = low_density_teleport_on
            instance["config"]["priority_low_density_threshold"] = str(low_density_threshold)
            instance["config"]["priority_low_density_range"] = str(low_density_range)
            instance["config"]["priority_low_density_cooldown"] = str(low_density_cooldown)
            
            # These are read from config, so no need to write back unless we want to ensure types/defaults
            # instance["config"]["priority_safety_distance"] = str(safety_distance)
            # ...

            if upper_threshold <= 0 or lower_threshold <= 0 or interval <= 0 or luring_range <= 0 or cluster_radius <= 0 or safety_distance <= 0 or safety_count <= 0 or stuck_time <= 0 or min_lure_distance < 0 or lure_ignore_time < 0 or lock_duration < 0:
                raise ValueError("所有數值必須大於 0 (部分可為 0)")
            if lower_threshold >= upper_threshold:
                raise ValueError("聚怪下限必須小於清怪上限")
        except ValueError as e:
            return messagebox.showerror(f"[{name}] 輸入錯誤", f"設定無效: {e}")

        self.log_message(f"--- [{name}] 準備開始自動聚怪 ---")
        self.log_message(f"[*] 起始地圖: {start_map_name}")

        instance["is_priority_targeting"] = True
        instance["priority_auto_on"] = False # Initialize state
        instance["last_tagged_key"] = None # Initialize last tagged target
        instance["tagged_monster_keys"] = [] # Keep track of tagged monsters
        instance["gathering_state"] = "GATHERING" # GATHERING, FIGHTING
        instance["priority_start_map_name"] = start_map_name # Store starting map
        if ui["priority_targeting_button"].winfo_exists():
            ui["priority_targeting_button"].config(text="停止")
        # Get pickup_range from config or default
        pickup_range = int(instance["config"].get("priority_pickup_range", "200"))

        instance["priority_targeting_thread"] = threading.Thread(
            target=self.priority_targeting_loop, 
            args=(name, upper_threshold, lower_threshold, skill_id, interval, luring_range, priority_pickup_list, priority_monster_blacklist, use_density_detection, cluster_radius, safety_distance, safety_count, use_stuck_teleport, stuck_time, pickup_range, min_lure_distance, lure_ignore_time, switch_on_hp_loss, lock_duration, low_density_teleport_on, low_density_threshold, low_density_range, low_density_cooldown), 
            daemon=True
        )
        instance["priority_targeting_thread"].start()

    def priority_targeting_loop(self, name, upper_threshold, lower_threshold, skill_id, interval, luring_range, priority_pickup_list, priority_monster_blacklist, use_density_detection, cluster_radius, safety_distance, safety_count, use_stuck_teleport, stuck_time, pickup_range, min_lure_distance, lure_ignore_time, switch_on_hp_loss, lock_duration, low_density_teleport_on, low_density_threshold, low_density_range, low_density_cooldown):
        instance = self.instances[name]
        ui = instance["ui"]
        api = instance["script_api"]

        def log_to_dialog(msg):
            # 輸出到全域日誌
            self.log_message(f"[{name}] {msg}")

        def update_status_display(state, attacker_count, upper_threshold, lower_threshold, 
                                  total_monsters, valid_count, blacklist_count, pending_name, density_info=None):
            if not self.root.winfo_exists():
                return
            
            def _update():
                if "priority_status_mode_label" not in ui or not ui["priority_status_mode_label"].winfo_exists():
                    return
                
                # 更新模式
                if state == 'GATHERING':
                    ui["priority_status_mode_label"].config(text="🎯 聚怪中", foreground="blue")
                elif state == 'FIGHTING':
                    ui["priority_status_mode_label"].config(text="⚔️ 清怪中", foreground="red")
                else:
                    ui["priority_status_mode_label"].config(text="未啟動", foreground="gray")
                
                # 更新進度條
                if upper_threshold > 0:
                    progress_percent = (attacker_count / upper_threshold) * 100
                    ui["priority_progress_bar"]["value"] = progress_percent
                ui["priority_progress_label"].config(text=f"{attacker_count}/{upper_threshold}")
                
                # 更新統計
                ui["priority_total_monsters_label"].config(text=f"{total_monsters} 隻")
                ui["priority_valid_targets_label"].config(text=f"{valid_count} 隻")
                ui["priority_blacklist_count_label"].config(text=f"{blacklist_count} 隻")
                
                # 更新等待中目標 (包含密度資訊)
                if pending_name:
                    if density_info:
                        ui["priority_pending_label"].config(text=f"{pending_name} | {density_info}")
                    else:
                        ui["priority_pending_label"].config(text=pending_name)
                else:
                    ui["priority_pending_label"].config(text="無")
            
            self.root.after(0, _update)

        log_to_dialog(f"--- 開始自動聚怪 (重構版) ---")
        log_to_dialog(f"--- 引怪技能 ID: {skill_id if skill_id else '未設定 (使用普攻)'} ---\n")

        # State variables
        pending_lure_target = None # { 'id': str, 'time': float, 'name': str, 'initial_hp': int }
        temp_ignore_list = {} # { id: expire_time }
        IGNORE_DURATION = 5.0 # Seconds to ignore a failed lure target
        LURE_TIMEOUT = max(5.0, stuck_time + 2.0) # Seconds to wait for aggro before giving up. Must be > stuck_time.
        start_map_name = instance.get("priority_start_map_name") # 記錄起始地圖

        try:
            while instance["is_priority_targeting"]:
                loop_start_time = time.time()
                current_time = loop_start_time
                
                # 1. Fetch Data
                player_info_str = api.get_info(201)
                objects_str = api.get_info(203)
                
                if not player_info_str or not objects_str:
                    time.sleep(1)
                    continue

                player_info = json.loads(player_info_str)
                objects_info = json.loads(objects_str)

                if player_info.get("status") != "success" or objects_info.get("status") != "success":
                    time.sleep(1)
                    continue
                
                # 2. 檢查地圖是否變更
                current_map_name = player_info.get("mapName", "未知地圖")
                if start_map_name and current_map_name != start_map_name:
                    log_to_dialog(f"偵測到地圖變更 (從 '{start_map_name}' 到 '{current_map_name}')。自動停止聚怪。")
                    self.log_message(f"[{name}] 偵測到地圖變更 (從 '{start_map_name}' 到 '{current_map_name}')。自動停止聚怪。")
                    instance["is_priority_targeting"] = False
                    continue # 立即結束此迴圈,觸發 finally 中的清理
                
                player_x, player_y = player_info.get("x"), player_info.get("y")
                all_monsters = [obj for obj in objects_info.get("data", []) if obj.get("type") == 6]
                all_dropped_items = [obj for obj in objects_info.get("data", []) if obj.get("type") == 3]
                
                
                # Update attackers count (排除黑名單怪物)
                attackers = [m for m in all_monsters 
                            if m.get("attackMe") and m.get("name") not in priority_monster_blacklist]
                attacker_count = len(attackers)

                # Calculate nearby monsters for safety check (排除黑名單)
                nearby_monsters = [m for m in all_monsters 
                                  if m.get("name") not in priority_monster_blacklist and 
                                  math.hypot(m.get("x", player_x) - player_x, m.get("y", player_y) - player_y) <= safety_distance]
                nearby_count = len(nearby_monsters)

                # --- Low Density Teleport Check ---
                if low_density_teleport_on:
                    last_teleport_time = instance.get("last_low_density_teleport_time", 0)
                    if current_time - last_teleport_time > low_density_cooldown:
                        # Count monsters in range
                        monsters_in_range = [m for m in all_monsters 
                                           if m.get("name") not in priority_monster_blacklist and 
                                           math.hypot(m.get("x", player_x) - player_x, m.get("y", player_y) - player_y) <= low_density_range]
                        
                        if len(monsters_in_range) < low_density_threshold:
                            log_to_dialog(f"範圍內怪物數量過少 ({len(monsters_in_range)} < {low_density_threshold}) -> 執行隨機順移")
                            
                            # Use Random Teleport Scroll
                            scroll_name = "瞬間移動卷軸(刻印)"
                            item_key_cache = instance.get("item_key_cache", {})
                            scroll_key = item_key_cache.get(scroll_name)
                            
                            if not scroll_key:
                                # Search inventory
                                try:
                                    inv_str = api.get_info(202)
                                    if inv_str:
                                        inv_data = json.loads(inv_str)
                                        if inv_data.get("status") == "success":
                                            for item in inv_data.get("data", []):
                                                if "瞬間移動卷軸" in item.get("itemName", ""): 
                                                    scroll_key = item.get("itemKey")
                                                    item_key_cache[scroll_name] = scroll_key 
                                                    break
                                except:
                                    pass
                            
                            if scroll_key:
                                api.use_item(str(scroll_key))
                                instance["last_low_density_teleport_time"] = current_time
                                time.sleep(1.0) # Wait for teleport
                                pending_lure_target = None # Reset target
                                continue
                            else:
                                log_to_dialog("無法順移: 找不到瞬間移動卷軸")

                # Clean up temp ignore list
                current_time = time.time()
                temp_ignore_list = {k: v for k, v in temp_ignore_list.items() if v > current_time}

                # --- Priority Item Pickup Logic (Preserved) ---
                if priority_pickup_list:
                    found_priority_item = None
                    for item in all_dropped_items:
                        item_name = item.get("name")
                        is_match = False
                        for pattern in priority_pickup_list:
                            if pattern.endswith('*'):
                                if item_name.startswith(pattern[:-1]):
                                    is_match = True
                                    break
                            elif item_name == pattern:
                                is_match = True
                                break
                        
                        if is_match:
                            # Check distance
                            item_x = item.get("x")
                            item_y = item.get("y")
                            if item_x is not None and item_y is not None:
                                dist = math.hypot(item_x - player_x, item_y - player_y)
                                if dist <= pickup_range:
                                    found_priority_item = item
                                    break
                            else:
                                # If no coordinates, assume valid (or ignore? assuming valid for now)
                                found_priority_item = item
                                break
                    
                    if found_priority_item:
                        item_name = found_priority_item.get("name")
                        item_key = found_priority_item.get("objectKey")
                        log_to_dialog(f"發現優先撿取物品: {item_name}，正在撿取。")
                        api.set_target(str(item_key))
                        api.attack_pickup()
                        time.sleep(0.5)
                        continue

                # --- State Machine ---
                current_state = instance.get("gathering_state", "GATHERING")
                
                # State Transition Check
                if current_state == 'GATHERING':
                    if attacker_count >= upper_threshold or nearby_count >= safety_count:
                        reason = f"達到聚怪上限 ({attacker_count}/{upper_threshold})" if attacker_count >= upper_threshold else f"近身怪物過多 ({nearby_count}/{safety_count})"
                        log_to_dialog(f"{reason} -> 切換至 FIGHTING")
                        instance["gathering_state"] = 'FIGHTING'
                        pending_lure_target = None # Clear pending
                        if not instance.get("priority_auto_on"):
                             api.toggle_auto(True)
                             instance["priority_auto_on"] = True
                        continue # Re-evaluate in next loop
                
                elif current_state == 'FIGHTING':
                    if attacker_count < lower_threshold and nearby_count < safety_count:
                        log_to_dialog(f"低於補怪下限 ({attacker_count}/{lower_threshold}) 且 周圍怪物安全 ({nearby_count}/{safety_count}) -> 切換至 GATHERING")
                        instance["gathering_state"] = 'GATHERING'
                        instance["tagged_monster_keys"] = [] # Reset tagged list (though we rely on attackMe now)
                        continue # Re-evaluate

                # --- Action Logic ---
                if current_state == 'FIGHTING':
                    # 主動切換攻擊最近的怪物
                    if attackers:
                        # 找出最近的攻擊中怪物
                        nearest_attacker = min(attackers, 
                                             key=lambda m: math.hypot(m.get("x", player_x) - player_x, 
                                                                     m.get("y", player_y) - player_y))
                        nearest_id = nearest_attacker.get("objectKey")
                        nearest_name = nearest_attacker.get("name")
                        nearest_dist = math.hypot(nearest_attacker.get("x") - player_x, 
                                                 nearest_attacker.get("y") - player_y)
                        
                        # 切換到最近的怪物
                        api.set_target(str(nearest_id))
                        # log_to_dialog(f"⚔️ 切換攻擊: {nearest_name} (距離: {nearest_dist:.1f})")

                elif current_state == 'GATHERING':
                    # Check if currently targeting a dropped item (picking up)
                    if player_info.get("targetType") == 3:
                        # log_to_dialog("正在撿取物品 (TargetType=3)，暫停聚怪邏輯...")
                        time.sleep(0.2)
                        continue

                    # Check Pending Lure
                    if pending_lure_target:
                        target_id = pending_lure_target['id']
                        target_name = pending_lure_target['name']
                        lure_time = pending_lure_target['time']
                        initial_hp = pending_lure_target.get('initial_hp', 0)
                        
                        # Find this monster in current list
                        monster_obj = next((m for m in all_monsters if str(m.get("objectKey")) == str(target_id)), None)
                        
                        if not monster_obj:
                            # log_to_dialog(f"目標 {target_name} 消失/死亡 -> 尋找下一個")  # 移除 LOG
                            pending_lure_target = None
                        else:
                            current_hp = monster_obj.get("curHP", 0)
                            
                            # 檢查血量是否減少 (引誘成功)
                            if initial_hp > 0 and current_hp > 0 and current_hp < initial_hp:
                                # 未啟用密度偵測: 立即切換目標
                                # 啟用密度偵測: 
                                #   - 若未勾選「血量減少切換」: 持續攻擊同一個目標 (不切換)
                                #   - 若勾選「血量減少切換」: 檢查鎖定時間，超過則切換
                                
                                should_switch = False
                                if not use_density_detection:
                                    should_switch = True
                                elif switch_on_hp_loss:
                                    # 密度模式 + 允許切換 -> 檢查鎖定時間
                                    time_locked = current_time - pending_lure_target['time']
                                    if time_locked >= lock_duration:
                                        should_switch = True
                                        # log_to_dialog(f"目標 {target_name} 鎖定超時 ({time_locked:.1f}s >= {lock_duration}s) 且血量減少 -> 切換")
                                
                                if should_switch:
                                    # 將成功引誘的目標加入短期忽略清單,避免立即重複選中
                                    temp_ignore_list[str(target_id)] = current_time + lure_ignore_time
                                    # log_to_dialog(f"✓ 目標 {target_name} 血量減少 ({initial_hp} -> {current_hp}) [成功] -> 切換目標 (忽略{lure_ignore_time:.0f}秒)")
                                    pending_lure_target = None
                                    # 移除 continue,讓程式繼續執行到「尋找新目標」邏輯,實現即時切換
                                # else: 保持 pending_lure_target,繼續攻擊同一個目標

                            # 只有在 pending_lure_target 仍存在時才執行卡點偵測和超時檢查
                            if pending_lure_target:
                                # 卡住/無法到達檢測 (Stuck Detection) - 改進版: 區間檢測
                                # 檢查自從上次檢查點以來 ('stuck_time' 秒前)，是否有足夠的移動
                                check_start_time = pending_lure_target.get('check_start_time')
                                check_start_x = pending_lure_target.get('check_start_x')
                                check_start_y = pending_lure_target.get('check_start_y')
                                
                                if check_start_time and check_start_x is not None:
                                    if current_time - check_start_time > stuck_time:
                                        # 時間到了，檢查這段時間內的移動距離
                                        interval_moved_dist = math.hypot(player_x - check_start_x, player_y - check_start_y)
                                        target_dist = math.hypot(monster_obj.get("x") - player_x, monster_obj.get("y") - player_y)
                                        
                                        # 如果這段時間內移動少於 2 步，且離目標還很遠 (>2)，判定為卡住
                                        if interval_moved_dist < 2.0 and target_dist > 2.0:
                                            log_to_dialog(f"目標 {target_name} 卡住判定 (在 {stuck_time}s 內僅移動 {interval_moved_dist:.1f})")
                                            
                                            if use_stuck_teleport:
                                                # 嘗試使用順移卷軸
                                                scroll_name = "瞬間移動卷軸(刻印)"
                                                item_key_cache = instance.get("item_key_cache", {})
                                                scroll_key = item_key_cache.get(scroll_name)
                                                
                                                # 如果快取沒有，嘗試即時搜尋背包
                                                if not scroll_key:
                                                    try:
                                                        inv_str = api.get_info(202)
                                                        if inv_str:
                                                            inv_data = json.loads(inv_str)
                                                            if inv_data.get("status") == "success":
                                                                for item in inv_data.get("data", []):
                                                                    if item.get("itemName") == scroll_name:
                                                                        scroll_key = item.get("itemKey")
                                                                        item_key_cache[scroll_name] = scroll_key # Update cache
                                                                        break
                                                    except:
                                                        pass

                                                if scroll_key:
                                                    log_to_dialog(f"-> 使用 {scroll_name} 脫離卡點")
                                                    api.use_item(str(scroll_key))
                                                    time.sleep(1.0) # 等待順移
                                                    pending_lure_target = None # Reset target
                                                    continue
                                                else:
                                                    log_to_dialog(f"-> 背包無 {scroll_name}，無法順移。")
                                            
                                            # 如果沒開啟順移或沒卷軸，則忽略該怪
                                            log_to_dialog(f"-> 放棄目標並忽略 10 秒")
                                            temp_ignore_list[str(target_id)] = current_time + 10.0
                                            pending_lure_target = None
                                            continue
                                        else:
                                            # 有移動，重置檢查點
                                            pending_lure_target['check_start_time'] = current_time
                                            pending_lure_target['check_start_x'] = player_x
                                            pending_lure_target['check_start_y'] = player_y

                                if current_time - lure_time > LURE_TIMEOUT:
                                    log_to_dialog(f"目標 {target_name} 引誘超時 ({LURE_TIMEOUT}s) -> 放棄並暫時忽略")
                                    temp_ignore_list[str(target_id)] = current_time + IGNORE_DURATION
                                    pending_lure_target = None
                                else:
                                    # Still waiting
                                    # log_to_dialog(f"等待 {target_name} 血量變化...") # Optional: too spammy?
                                    pass
                    
                    else:
                        # No pending target, find a new one
                        valid_targets = []
                        for m in all_monsters:
                            mid = str(m.get("objectKey"))
                            # Filter conditions
                            if m.get("attackMe"): continue # Already attacking
                            if mid in temp_ignore_list: continue # Recently failed
                            if m.get("name") in priority_monster_blacklist: continue
                            
                            dist = math.hypot(m.get("x", player_x) - player_x, m.get("y", player_y) - player_y)
                            if dist > luring_range: continue  # 超出引怪範圍
                            if dist < min_lure_distance: continue  # 太近不引誘 (避免引誘身邊的怪)
                            
                            valid_targets.append(m)
                        
                        if not valid_targets:
                            # 沒有符合引誘條件的目標,嘗試切換到最近的怪物(即使不符合條件)
                            if all_monsters:
                                # 找出範圍內最近的怪物(忽略所有篩選條件,除了距離)
                                nearby_monsters = [m for m in all_monsters 
                                                 if math.hypot(m.get("x", player_x) - player_x, 
                                                             m.get("y", player_y) - player_y) <= luring_range]
                                
                                if nearby_monsters:
                                    nearest = min(nearby_monsters, 
                                                key=lambda m: math.hypot(m.get("x", player_x) - player_x, 
                                                                       m.get("y", player_y) - player_y))
                                    nearest_id = nearest.get("objectKey")
                                    nearest_name = nearest.get("name")
                                    nearest_dist = math.hypot(nearest.get("x") - player_x, nearest.get("y") - player_y)
                                    
                                    # log_to_dialog(f"⚠️ 無可引誘目標 -> 切換到最近怪物: {nearest_name} (距離: {nearest_dist:.1f})")
                                    api.set_target(str(nearest_id))
                            # else: 範圍內完全沒有怪物,讓 AUTO 處理
                        else:
                            # Selection Logic (Density or Distance)
                            target_to_tag = None
                            target_density_score = None  # 儲存密度分數
                            if use_density_detection:
                                # ... (Density logic preserved) ...
                                target_scores = []
                                for target_a in valid_targets:
                                    score = 0
                                    for target_b in all_monsters:
                                        if target_a == target_b: continue
                                        d = math.hypot(target_a.get("x") - target_b.get("x"), target_a.get("y") - target_b.get("y"))
                                        if d <= cluster_radius:
                                            score += 1
                                    target_scores.append({"monster": target_a, "score": score})
                                
                                if target_scores:
                                    max_score = max(s["score"] for s in target_scores)
                                    top_targets = [s["monster"] for s in target_scores if s["score"] == max_score]
                                    target_to_tag = min(top_targets, key=lambda m: math.hypot(m.get("x") - player_x, m.get("y") - player_y))
                                    target_density_score = max_score  # 儲存密度分數
                            else:
                                target_to_tag = min(valid_targets, key=lambda m: math.hypot(m.get("x") - player_x, m.get("y") - player_y))
                            
                            if target_to_tag:
                                tid = target_to_tag.get("objectKey")
                                tname = target_to_tag.get("name")
                                dist = math.hypot(target_to_tag.get("x") - player_x, target_to_tag.get("y") - player_y)
                                
                                # 顯示密度資訊(如果啟用)
                                density_info = f" | 密度: {target_density_score}" if use_density_detection and target_density_score is not None else ""
                                # log_to_dialog(f"🎯 鎖定目標: {tname} (距離: {dist:.1f}){density_info} -> 執行引誘")
                                api.set_target(str(tid))
                                if skill_id:
                                    api.use_skill(skill_id, str(tid))
                                else:
                                    api.attack_pickup()
                                
                                pending_lure_target = {
                                    'id': str(tid),
                                    'time': time.time(),
                                    'name': tname,
                                    'initial_hp': target_to_tag.get("curHP", 0),
                                    'check_start_time': time.time(), # 初始化檢查點時間
                                    'check_start_x': player_x,       # 初始化檢查點座標
                                    'check_start_y': player_y,
                                    'density_score': target_density_score  # 儲存密度分數到 pending_lure_target
                                }
                                # We do NOT sleep here heavily, we let the loop check for aggro

                # 計算統計數據並更新狀態顯示
                blacklist_count = sum(1 for m in all_monsters if m.get("name") in priority_monster_blacklist)
                pending_name = pending_lure_target['name'] if pending_lure_target else None
                valid_count = len(valid_targets) if 'valid_targets' in locals() else 0
                
                # 準備密度資訊
                density_info = None
                if pending_lure_target and use_density_detection:
                    density_score = pending_lure_target.get('density_score')
                    if density_score is not None:
                        density_info = f"密度: {density_score} 隻 (半徑 {cluster_radius})"
                
                update_status_display(
                    current_state, 
                    attacker_count, 
                    upper_threshold, 
                    lower_threshold,
                    len(all_monsters),
                    valid_count,
                    blacklist_count,
                    pending_name,
                    density_info
                )

                # Dynamic Sleep
                elapsed = time.time() - loop_start_time
                sleep_time = max(0.1, interval - elapsed) # Ensure at least small sleep
                
                # Break sleep into chunks for responsiveness
                end_sleep = time.time() + sleep_time
                while time.time() < end_sleep:
                    if not instance["is_priority_targeting"]:
                        break
                    time.sleep(0.1)

        except Exception as e:
            log_to_dialog(f"發生錯誤: {e}")
            import traceback
            traceback.print_exc()
        finally:
            instance["is_priority_targeting"] = False
            if "priority_targeting_button" in ui and ui["priority_targeting_button"].winfo_exists():
                ui["priority_targeting_button"].config(state='normal', text="開始")
            log_to_dialog("--- 自動聚怪結束 ---")
            self.log_message(f"[{name}] 自動聚怪停止，AUTO 保持開啟。")

            if self.root.winfo_exists() and name in self.instances:
                def _reset_ui():
                    instance["is_priority_targeting"] = False
                    instance["priority_auto_on"] = False
                    if "priority_targeting_button" in ui and ui["priority_targeting_button"].winfo_exists():
                        ui["priority_targeting_button"].config(state='normal', text="開始")
                    # 重置狀態顯示
                    if "priority_status_mode_label" in ui and ui["priority_status_mode_label"].winfo_exists():
                        ui["priority_status_mode_label"].config(text="未啟動", foreground="gray")
                        ui["priority_progress_bar"]["value"] = 0
                        ui["priority_progress_label"].config(text="0/0")
                        ui["priority_total_monsters_label"].config(text="0 隻")
                        ui["priority_valid_targets_label"].config(text="0 隻")
                        ui["priority_blacklist_count_label"].config(text="0 隻")
                        ui["priority_pending_label"].config(text="無")
                self.root.after(0, _reset_ui)
    def apply_custom_styles(self):
        try:
            padding_val = int(self.button_padding_entry.get())
            self.style.configure('Taller.TButton', padding=(0, padding_val))
            # 配置紅色按鈕樣式
            self.style.configure('Red.Taller.TButton', padding=(0, padding_val), foreground='red',font=('微軟正黑體', 14)) 
            self.log_message(f"[樣式] 已套用按鈕高度: {padding_val}px")
        except (ValueError, tk.TclError) as e:
            self.log_message(f"[錯誤] 按鈕高度設定無效: {e}")
            messagebox.showerror("輸入錯誤", "按鈕高度必須是有效的整數。")

        try:
            height_val = int(self.log_height_entry.get())
            if height_val > 0:
                self.log_area.config(height=height_val)
                self.log_message(f"[樣式] 已套用日誌高度: {height_val}行")
            else:
                raise ValueError("Height must be positive")
        except (ValueError, tk.TclError) as e:
            self.log_message(f"[錯誤] 日誌高度設定無效: {e}")
            messagebox.showerror("輸入錯誤", "日誌高度必須是有效的正整數。")

    def check_frida_server_running(self, name, adb_path, device_serial):
        """檢查 frida-server 是否已在執行
        
        Returns:
            tuple: (is_running: bool, pid: str or None)
        """
        try:
            # 嘗試使用 ps -A (Android 8+)
            command = [adb_path, "-s", device_serial, "shell", "su", "-c", "ps -A"]
            self.log_message(f"[{name}] 檢查 frida-server 狀態...")
            process = subprocess.run(command, capture_output=True, text=True, 
                                    encoding='utf-8', errors='ignore', 
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            
            if not process.stdout or "frida-server" not in process.stdout:
                # 嘗試舊版 ps 指令
                command = [adb_path, "-s", device_serial, "shell", "su", "-c", "ps"]
                process = subprocess.run(command, capture_output=True, text=True, 
                                        encoding='utf-8', errors='ignore', 
                                        creationflags=subprocess.CREATE_NO_WINDOW)
            
            if process.stdout:
                for line in process.stdout.splitlines():
                    if "frida-server" in line and "grep" not in line:
                        parts = line.split()
                        if len(parts) > 1 and parts[1].isdigit():
                            return True, parts[1]  # 返回 True 和 PID
            
            return False, None
        except Exception as e:
            self.log_message(f"[{name}] 檢查 frida-server 時發生錯誤: {e}")
            return False, None

    def check_environment_status(self, name):
        """檢查環境狀態並更新指示器"""
        instance, ui = self.instances[name], self.instances[name]["ui"]
        
        # 重置所有狀態為灰色
        ui["adb_status_label"].config(text="● ADB 連線", foreground="gray")
        ui["forward_status_label"].config(text="● 端口轉發", foreground="gray")
        ui["frida_status_label"].config(text="● Frida Server", foreground="gray")
        
        adb_path = ui["adb_path_entry"].get()
        device_serial = ui["device_serial_entry"].get()
        forward_port = ui["forward_port_entry"].get()
        
        if not all([adb_path, device_serial, forward_port]):
            self.log_message(f"[{name}] 請先填寫 ADB 路徑、裝置序號和轉發 Port")
            return
        
        # 禁用檢查按鈕
        ui["env_check_button"].config(state='disabled', text="檢查中...")
        
        # 在背景執行檢查
        threading.Thread(target=self._check_environment_status_thread, 
                        args=(name, adb_path, device_serial, forward_port), 
                        daemon=True).start()

    def _check_environment_status_thread(self, name, adb_path, device_serial, forward_port):
        """背景執行環境狀態檢查"""
        instance, ui = self.instances[name], self.instances[name]["ui"]
        
        try:
            # 1. 檢查 ADB 連線
            self.log_message(f"[{name}] 正在檢查 ADB 連線...")
            adb_ok = self.ensure_adb_device(name, adb_path, device_serial)
            self.root.after(0, lambda: self._update_status_indicator(
                ui["adb_status_label"], "ADB 連線", adb_ok))
            
            # 2. 檢查端口轉發
            self.log_message(f"[{name}] 正在檢查端口轉發...")
            forward_ok = self._check_port_forward(name, adb_path, forward_port)
            self.root.after(0, lambda: self._update_status_indicator(
                ui["forward_status_label"], "端口轉發", forward_ok))
            
            # 3. 檢查 Frida Server
            self.log_message(f"[{name}] 正在檢查 Frida Server...")
            frida_ok, pid = self.check_frida_server_running(name, adb_path, device_serial)
            status_text = f"Frida Server (PID: {pid})" if frida_ok else "Frida Server"
            self.root.after(0, lambda st=status_text, ok=frida_ok: self._update_status_indicator(
                ui["frida_status_label"], st, ok))
            
            # 顯示總結
            if all([adb_ok, forward_ok, frida_ok]):
                self.log_message(f"[{name}] ✓ 環境檢查完成: 所有項目正常")
            else:
                self.log_message(f"[{name}] ⚠ 環境檢查完成: 部分項目異常")
        
        except Exception as e:
            self.log_message(f"[{name}] 環境檢查時發生錯誤: {e}")
        
        finally:
            # 重新啟用檢查按鈕
            self.root.after(0, lambda: ui["env_check_button"].config(state='normal', text="檢查"))

    def _update_status_indicator(self, label_widget, text, is_ok):
        """更新狀態指示器的顏色和文字"""
        color = "green" if is_ok else "red"
        label_widget.config(text=f"● {text}", foreground=color)

    def _check_port_forward(self, name, adb_path, forward_port):
        """檢查端口轉發是否已設定"""
        try:
            command = [adb_path, "forward", "--list"]
            process = subprocess.run(command, capture_output=True, text=True,
                                    encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
            
            if process.stdout:
                # 檢查是否包含目標端口轉發規則
                target_rule = f"tcp:{forward_port}"
                if target_rule in process.stdout:
                    self.log_message(f"[{name}] ✓ 端口轉發已設定: {forward_port}")
                    return True
            
            self.log_message(f"[{name}] ✗ 端口轉發未設定")
            return False
        except Exception as e:
            self.log_message(f"[{name}] ✗ 檢查端口轉發時發生錯誤: {e}")
            return False

    def connect_thread(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        ui["connect_button"].config(state='disabled', text="連接中...")
        threading.Thread(target=self.establish_connection, args=(name,), daemon=True).start()

    def establish_connection(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            self.log_message(f"--- [{name}] 開始連接 ---")
            port = ui["port_entry"].get()
            if not port.isdigit():
                raise ValueError("端口號必須是數字。")
            
            # --- 自動檢測並啟動 Frida ---
            adb_path = ui["adb_path_entry"].get()
            device_serial = ui["device_serial_entry"].get()
            forward_port = ui["forward_port_entry"].get()
            
            # 檢查必要參數是否已設定
            if adb_path and device_serial and forward_port:
                # 檢查 frida-server 是否已在執行
                is_running, pid = self.check_frida_server_running(name, adb_path, device_serial)
                
                if is_running:
                    self.log_message(f"[{name}] -> frida-server 已在執行 (PID: {pid}),跳過啟動步驟")
                else:
                    self.log_message(f"[{name}] -> frida-server 未運行,自動啟動 Frida 環境...")
                    
                    # 確保 ADB 裝置連線正常
                    if not self.ensure_adb_device(name, adb_path, device_serial):
                        raise Exception("ADB 裝置連線失敗,無法啟動 Frida")
                    
                    # 執行 Frida 設定 (包括 forward 和啟動 frida-server)
                    self.execute_frida_setup(name, adb_path, device_serial, forward_port)
                    
                    # 等待一下確保 frida-server 完全啟動
                    time.sleep(2)
                    
                    # 再次檢查是否啟動成功
                    is_running_after, pid_after = self.check_frida_server_running(name, adb_path, device_serial)
                    if is_running_after:
                        self.log_message(f"[{name}] -> Frida 自動啟動成功 (PID: {pid_after})")
                    else:
                        raise Exception("Frida 自動啟動失敗,請手動檢查")
            else:
                self.log_message(f"[{name}] -> 未設定 ADB 參數,跳過 Frida 自動檢測")
            # --- 自動檢測並啟動 Frida 結束 ---
            
            pid, device = LineageM.get_pid_by_package(LineageM.package_name, port, logger=lambda msg: self.log_message(f"[{name}] {msg}"))
            if not pid or not device:
                raise Exception("找不到目標進程，請確認遊戲或應用已開啟。")
            
            self.log_message(f"[{name}] 找到進程 {pid}，正在附加...")
            
            # --- Fix: Detach existing session if any ---
            if instance.get("session"):
                try:
                    self.log_message(f"[{name}] 偵測到舊的連線，正在分離...")
                    instance["session"].detach()
                    self.log_message(f"[{name}] 舊連線已分離。")
                except Exception as e:
                    self.log_message(f"[{name}] 分離舊連線時發生錯誤 (可能已斷開): {e}")
                finally:
                    instance["session"] = None
            # -------------------------------------------

            instance["session"] = device.attach(pid)
            self.log_message(f"[{name}] 成功附加到進程！正在載入RPC主腳本...")

            c0391_class = ui["c0391_class_name_entry"].get()
            socket_method = ui["socket_utils_method_entry"].get()
            use_item_method = ui["use_item_method_name_entry"].get()
            auto_method = ui["auto_method_entry"].get()
            skill_use_method = ui["skill_use_method_name_entry"].get()
            target_method = ui["target_method_name_entry"].get()
            attack_pickup_method = ui["attack_pickup_method_name_entry"].get()
            moveto_classname = ui["moveto_classname_entry"].get()
            self.log_message(f"[{name}] 載入 Auto Method: '{auto_method}'")
            self.log_message(f"[{name}] 載入 SkillUse Method: '{skill_use_method}'")
            self.log_message(f"[{name}] 載入 Target Method: '{target_method}'")
            self.log_message(f"[{name}] 載入 Attack/Pickup Method: '{attack_pickup_method}'")
            self.log_message(f"[{name}] 載入 MoveTo Classname: '{moveto_classname}'")
            
            script = LineageM.create_main_monitor_script(instance["session"], 
                                                         c0391_class_name=c0391_class, 
                                                         socket_utils_method=socket_method, 
                                                         use_item_method_name=use_item_method,
                                                         auto_method_name=auto_method,
                                                         skill_use_method_name=skill_use_method,
                                                         target_method_name=target_method,
                                                         attack_pickup_method_name=attack_pickup_method,
                                                         moveto_classname=moveto_classname)
            script.on('message', lambda msg, data, n=name: self.on_message_display(msg, data, n))
            script.load()
            instance["script_api"] = script.exports_sync
            instance["script_object"] = script
            self.log_message(f"[{name}] RPC主腳本載入成功！")

            def _pre_fetch_keys():
                time.sleep(1) # 稍微延遲，確保連接穩定
                self.log_message(f"--- [{name}] 連線成功，預先讀取回村卷軸 Key ---")
                api = instance.get("script_api")
                if not api: return

                item_key_cache = instance.setdefault("item_key_cache", {})
                scroll_names = ["傳送回家的卷軸(刻印)", "遺忘之傳送回家的卷軸(刻印)", "瞬間移動卷軸(刻印)"]
                
                try:
                    inv_str = api.get_info(202)
                    if not inv_str:
                        self.log_message(f"[{name}] 預讀失敗: 無法獲取背包列表。")
                        return
                    
                    inv_data = json.loads(inv_str)
                    if inv_data.get("status") != "success": return

                    found_names = set()
                    for item in inv_data.get("data", []):
                        item_name = item.get("itemName")
                        if item_name in scroll_names:
                            item_key_cache[item_name] = item.get("itemKey")
                            self.log_message(f"[{name}] -> 預讀成功: '{item_name}' Key 已存入快取")
                            found_names.add(item_name)
                    
                    not_found_names = set(scroll_names) - found_names
                    if not_found_names:
                        for scroll_name in not_found_names:
                            self.log_message(f"[{name}] -> 在背包中未找到 '{scroll_name}'")

                except Exception as e:
                    self.log_message(f"[{name}] 預讀 Key 時發生錯誤: {e}")

            threading.Thread(target=_pre_fetch_keys, daemon=True).start()
            
            self.root.after(0, lambda: self.set_action_buttons_state(name, 'normal'))
            if "barrier_toggle_button" in ui:
                self.root.after(0, lambda: ui["barrier_toggle_button"].config(state='normal'))
            self.root.after(0, lambda: ui["connect_button"].config(state='normal', text="已連接"))

        except Exception as e:
            self.log_message(f"[{name}] 連接失敗: {e}")
            self.root.after(0, lambda: messagebox.showerror(f"[{name}] 連接錯誤", f"發生錯誤: {e}"))
            self.root.after(0, lambda: self.reset_connect_button(name))

    def process_and_log_json(self, name, payload_str, purpose=None):
        try:
            ui = self.instances[name]["ui"]
            keep_fields_str = ui["keep_fields_entry"].get().strip()
            parsed_data = json.loads(payload_str)

            if purpose == "list_players" and parsed_data.get("status") == "success":
                all_objects = parsed_data.get("data", [])
                players = [obj for obj in all_objects if obj.get("type") == 2]
                
                clans = {}
                for player in players:
                    clan_name = player.get("clanName", "").strip()
                    if not clan_name:
                        clan_name = "無血盟"
                    if clan_name not in clans:
                        clans[clan_name] = []
                    clans[clan_name].append(player.get("name", "未知玩家"))

                # 如果在列出玩家時提供了保留欄位，則將其用作血盟過濾器
                if keep_fields_str:
                    allowed_clans = {c.strip() for c in keep_fields_str.split(',') if c.strip()}
                    clans = {cn: mem for cn, mem in clans.items() if cn in allowed_clans}

                self.log_message(f"--- [{name}] 周圍物件與玩家分析 ---")
                self.log_message(f"偵測到 {len(all_objects)} 個物件，其中玩家共 {len(players)} 名。")

                if not players:
                    self.log_message(f"周圍沒有玩家。")
                else:
                    # Sort clans by name, but keep "無血盟" at the end
                    sorted_clans = sorted(clans.items(), key=lambda item: (item[0] == "無血盟", item[0]))
                    
                    self.log_message(f"--- 血盟分類 (共 {len(clans)} 個血盟) ---")
                    for clan_name, members in sorted_clans:
                        self.log_message(f"[{clan_name}] ({len(members)}名): {', '.join(members)}")
                        self.log_message("") # Add a blank line
                
                self.log_message(f"--- [{name}] 分析完畢 ---")
                return

            elif purpose == "list_objects" and parsed_data.get("status") == "success":
                all_objects = parsed_data.get("data", [])
                
                # 如果有輸入保留欄位，則進行過濾
                if keep_fields_str:
                    keywords = [k.strip() for k in keep_fields_str.split(',') if k.strip()]
                    if keywords:
                        all_objects = [obj for obj in all_objects if any(k in obj.get("name", "") for k in keywords)]

                type_map = {
                    2: "玩家",
                    6: "怪物/NPC",
                    22: "特殊物件",
                    3: "掉落物"
                }
                
                # 職業對照表
                class_map = {
                    1: "騎士",
                    2: "妖精",
                    3: "法師",
                    4: "黑妖",
                    5: "龍鬥",
                    7: "狂戰",
                    8: "王族",
                    34: "槍手",
                    52: "暗騎",
                    81: "聖劍",
                    94: "死神",
                    111: "雷神",
                    142: "魔劍"
                }
                
                categorized_objects = {obj_type: [] for obj_type in type_map.values()}
                categorized_objects["其他"] = []

                for obj in all_objects:
                    obj_type = obj.get("type")
                    type_name = type_map.get(obj_type, "其他")
                    categorized_objects[type_name].append(obj)

                self.log_message(f"--- [{name}] 周圍物件分析 ---")
                self.log_message(f"偵測到 {len(all_objects)} 個物件。")

                for type_name, objects in categorized_objects.items():
                    if objects:
                        self.log_message(f"\n--- {type_name} ({len(objects)}個) ---")
                        
                        # 如果是玩家，按職業排序並分組顯示
                        if type_name == "玩家":
                            # 按 earthObjectID 排序
                            sorted_players = sorted(objects, key=lambda obj: obj.get('earthObjectID', 999))
                            
                            # 按職業分組
                            current_class_id = None
                            class_count = 0
                            
                            for obj in sorted_players:
                                obj_name = obj.get('name', 'N/A')
                                x = obj.get('x', 'N/A')
                                y = obj.get('y', 'N/A')
                                earth_obj_id = obj.get('earthObjectID', 0)
                                class_name = class_map.get(earth_obj_id, f"未知({earth_obj_id})")
                                
                                # 如果是新的職業，顯示職業標題
                                if earth_obj_id != current_class_id:
                                    if current_class_id is not None:
                                        # 顯示上一個職業的統計
                                        pass
                                    current_class_id = earth_obj_id
                                    class_count = 1
                                    self.log_message(f"\n  [{class_name}]")
                                else:
                                    class_count += 1
                                
                                self.log_message(f"    名稱: {obj_name}, 座標: ({x}, {y})")
                        else:
                            # 其他物件正常顯示
                            for obj in objects:
                                obj_name = obj.get('name', 'N/A')
                                x = obj.get('x', 'N/A')
                                y = obj.get('y', 'N/A')
                                object_key = obj.get('objectKey', 'N/A')
                                self.log_message(f"  名稱: {obj_name}, 座標: ({x}, {y}), Key: {object_key}")

                self.log_message(f"\n--- [{name}] 分析完畢 ---")
                return

            if not keep_fields_str:
                formatted_payload = json.dumps(parsed_data, indent=2, ensure_ascii=False)
                self.log_message(f"[{name} Frida]:\n{formatted_payload}")
                return

            keep_fields = [f.strip() for f in keep_fields_str.split(',') if f.strip()]
            data_to_filter = []
            is_single_item = False
            is_wrapped_in_data = False

            if isinstance(parsed_data, list):
                data_to_filter = parsed_data
            elif isinstance(parsed_data, dict):
                if 'data' in parsed_data and isinstance(parsed_data['data'], list):
                    data_to_filter = parsed_data['data']
                    is_wrapped_in_data = True
                else:
                    data_to_filter = [parsed_data]
                    is_single_item = True
            else:
                self.log_message(f"[{name} Frida]: {payload_str}")
                return

            filtered_list = []
            for item in data_to_filter:
                if isinstance(item, dict):
                    filtered_item = {key: item[key] for key in keep_fields if key in item}
                    if filtered_item:
                        filtered_list.append(filtered_item)
            
            final_result = None
            if is_single_item:
                final_result = filtered_list[0] if filtered_list else {}
            elif is_wrapped_in_data:
                final_result = {'data': filtered_list}
            else:
                final_result = filtered_list

            if not final_result or (isinstance(final_result, dict) and not final_result) or \
               (isinstance(final_result, dict) and 'data' in final_result and not final_result['data']) or \
               (isinstance(final_result, list) and not final_result):
                self.log_message(f"[{name} Frida 過濾後]: (沒有符合的欄位，結果為空)")
            else:
                filtered_payload = json.dumps(final_result, indent=2, ensure_ascii=False)
                self.log_message(f"[{name} Frida 過濾後]:\n{filtered_payload}")

        except (json.JSONDecodeError, TypeError):
            self.log_message(f"[{name} Frida]: {payload_str})")
        except Exception as e:
            self.log_message(f"[{name}] GUI處理錯誤: {e}")

    def on_message_display(self, message, data, name):
        if message['type'] == 'send':
            # 檢查 payload 是否以 "[RPC]" 開頭，如果是則不處理，以抑制日誌
            if isinstance(message['payload'], str) and message['payload'].startswith('[RPC]'):
                pass # 忽略 RPC 訊息
            else:
                self.process_and_log_json(name, message['payload'])
        elif message['type'] == 'error':
            self.log_message(f"[❌] [{name}] Frida 腳本錯誤: {message['description']}")

    def run_script_thread(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        if instance["is_monitoring"]:
            return messagebox.showwarning(f"[{name}] 監控中", "請先停止監控。")
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接'。")
        
        input_value = ui["input_entry"].get()
        if not input_value.isdigit():
            return messagebox.showerror(f"[{name}] 輸入錯誤", "指令代碼必須是數字。")
        
        ui["run_button"].config(state='disabled', text="執行中...")
        threading.Thread(target=self.execute_frida_script, args=(name, int(input_value)), daemon=True).start()

    def execute_frida_script(self, name, value, purpose=None):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            if self.root.winfo_exists():
                self.root.after(0, lambda: ui["run_button"].config(state='disabled', text="執行中..."))
            self.log_message(f"--- [{name}] 執行指令: {value} ---")
            api = instance["script_api"]
            result = api.get_info(value)
            self.process_and_log_json(name, result, purpose)
        except Exception as e:
            self.handle_script_error(e, name)
        finally:
            if self.root.winfo_exists():
                self.root.after(0, lambda: ui["run_button"].config(state='normal', text="執行"))

    def run_quick_command_thread(self, name, command_code, purpose=None):
        instance = self.instances[name]
        if instance["is_monitoring"]:
            return messagebox.showwarning(f"[{name}] 監控中", "請先停止監控。")
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接'。")
        
        threading.Thread(target=self.execute_quick_frida_script, args=(name, command_code, purpose), daemon=True).start()

    def execute_quick_frida_script(self, name, value, purpose=None):
        instance = self.instances[name]
        try:
            self.log_message(f"--- [{name}] 執行指令: {value} ---")
            api = instance["script_api"]
            result = api.get_info(value)
            self.process_and_log_json(name, result, purpose)
        except Exception as e:
            self.handle_script_error(e, name)

    def list_nearby_players_thread(self, name):
        instance = self.instances[name]
        if instance["is_monitoring"]:
            messagebox.showwarning(f"[{name}] 監控中", "請先停止監控。")
            return
        if not instance.get("script_api"):
            messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接'。")
            return
        
        self.log_message(f"--- [{name}] 正在獲取周圍玩家資訊... ---")
        threading.Thread(target=self.execute_quick_frida_script, args=(name, 203, "list_players"), daemon=True).start()

    def handle_script_error(self, e, name):
        error_message = str(e).lower()
        self.log_message(f"[{name} 發生錯誤]: {e}")
        if "session is detached" in error_message or "process is terminated" in error_message:
            self.log_message(f"[{name}] 連線已中斷，請重新連接。")
            if name in self.instances:
                self.instances[name]["session"] = None
                self.instances[name]["is_monitoring"] = False
                self.instances[name]["script_api"] = None
                self.instances[name]["script_object"] = None
                if self.root.winfo_exists():
                    self.root.after(0, lambda: self.reset_connect_button(name))

    def reset_connect_button(self, name):
        if self.root.winfo_exists() and name in self.instances:
            ui = self.instances[name]["ui"]
            ui["connect_button"].config(state='normal', text="連接")
            self.set_action_buttons_state(name, 'disabled')
            ui["barrier_toggle_button"].config(state='disabled')

    def set_action_buttons_state(self, name, state):
        ui = self.instances[name]["ui"]
        buttons = [
            "run_button", "back_button", "moveto_button", "monitor_button", 
            "use_item_button", "start_auto_button", "stop_auto_button",
            "seq_move_manage_button", "start_seq_move_button", "monster_detection_button",
            "use_skill_button", "select_skill_button", "priority_select_skill_button", "specify_target_button",
            "edit_specify_targets_button", "timed_target_button", "timed_skill_button", "advanced_features_button",
            "seq_move_control_button", "patrol_control_button", "get_objects_button", "list_players_button",
            "auto_barrier_button", "test_features_button", "general_afk_button"
        ]
        for btn_key in buttons:
            if btn_key in ui and ui[btn_key].winfo_exists():
                ui[btn_key].config(state=state)
        # Stop buttons have special logic
        if 'stop_seq_move_button' in ui and ui['stop_seq_move_button'].winfo_exists():
            ui['stop_seq_move_button'].config(state='disabled')


    def show_parameter_info(self, name):
        info_text = r"""
C0391 Class Name：SocketUtils.m1134(6444, new C0323(211)); 在GameHelper找211指令 然後進入C0323就可以取的 -\"ቌ.ᣇ.ᶬ.ಞ.㚽.Ố"                                               
MoveTo Classname：在GameHelper 找402指令 就可以取的\"混淆變數\" -䄼         
UseItem Method Name：在GameHelper 找404指令 就可以取的\"混淆變數\" -䇪      
SocketUtils Method：路徑 com.lineagem.botv3.util 取的\"混淆變數\" -ᶬ 
Auto指令：在GameHelper 找403指令 可以找到Auto啟動與關閉的控制項
skinuse：在GameHelper 找409指令(int i ,long j)
指定目標：在GameHelper 找418指令(long j) j=目標 objectKey
攻擊或撿取：在GameHelper 找428指令() 指定目標後調用
攻擊或撿取：在GameHelper 找428指令() 指定目標後調用
打包：c:\Users\small\AppData\Local\Microsoft\WindowsApps\python3.13.exe -m PyInstaller -F -w gui.py        """
        self.log_message(f"[{name}] {info_text}")

    def show_command_params_info(self, name):
        info_text = """
//參數 201指令會返回人物腳色位置及其他訊息
//參數 203指令會返回所有周圍的NPC訊息
//參數 206指令會返回人物腳色Buff狀態
//參數 218指令會返回人物腳色擁有技能列表 參數 409技能使用
//參數 220指令會返回現在伺服器所有腳色名稱
//參數 202指令會返回人物腳色包包物品
//參數 213指令會返回一組座標用途不明"""
        self.log_message(f"[{name}] {info_text}")

    def open_target_list_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 編輯監控目標")
        dialog.transient(self.root)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)

        ttk.Label(main_frame, text="請輸入要監控的目標名稱，每行一個:").pack(anchor='w', pady=(0, 5))

        # --- Search Frame ---
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=5)
        
        search_label = ttk.Label(search_frame, text="搜尋:")
        search_label.pack(side=tk.LEFT, padx=(0, 5))
        
        search_entry = ttk.Entry(search_frame)
        search_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

        dialog_text_area = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD)
        dialog_text_area.pack(expand=True, fill=tk.BOTH)
        
        search_button = ttk.Button(search_frame, text="尋找", style='Taller.TButton', 
                                   command=lambda: self.search_in_text_widget(dialog_text_area, search_entry))
        search_button.pack(side=tk.LEFT)
        
        dialog_text_area.tag_configure("found", background="yellow", foreground="black")
        dialog_text_area.tag_configure("duplicate", background="orange", foreground="black")

        current_targets = ui["target_entry"].get("1.0", tk.END).strip()
        dialog_text_area.insert("1.0", current_targets)

        # --- Settings Frame ---
        settings_frame = ttk.Frame(main_frame)
        settings_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(settings_frame, text="監控間隔(秒):").pack(side=tk.LEFT)
        interval_entry = ttk.Entry(settings_frame, width=10)
        interval_entry.pack(side=tk.LEFT, padx=(5, 0))
        interval_entry.insert(0, ui["target_interval_entry"].get())

        def save_and_close():
            new_targets = dialog_text_area.get("1.0", tk.END).strip()
            ui["target_entry"].delete("1.0", tk.END)
            ui["target_entry"].insert("1.0", new_targets)
            
            # Save interval
            ui["target_interval_entry"].delete(0, tk.END)
            ui["target_interval_entry"].insert(0, interval_entry.get())
            
            self.log_message(f"[{name}] 已更新監控目標列表與設定。")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        format_button = ttk.Button(button_frame, text="切換格式",
                                   command=lambda: self.toggle_target_format(dialog_text_area),
                                   style='Taller.TButton')
        format_button.pack(side=tk.LEFT, padx=(0, 5))

        check_button = ttk.Button(button_frame, text="檢查重複", 
                                  command=lambda: self.check_for_duplicates(dialog_text_area), 
                                  style='Taller.TButton')
        check_button.pack(side=tk.LEFT, padx=5)

        ok_button = ttk.Button(button_frame, text="儲存並關閉", command=save_and_close, style='Taller.TButton')
        ok_button.pack(side=tk.RIGHT, padx=5)
        cancel_button = ttk.Button(button_frame, text="取消", command=dialog.destroy, style='Taller.TButton')
        cancel_button.pack(side=tk.RIGHT)

        # Center the dialog
        dialog.resizable(False, False)
        dialog.update_idletasks()
        dialog_width = 500
        dialog_height = 500
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)

    def open_overlay_advanced_settings_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Overlay 進階設定 - {name}")
        dialog.geometry("200x200")
        
        frame = ttk.Frame(dialog, padding="10")
        frame.pack(expand=True, fill=tk.BOTH)
        
        def create_row(label_text, entry_key, default_val):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label_text, width=15).pack(side=tk.LEFT)
            entry = ttk.Entry(row)
            entry.pack(side=tk.RIGHT, expand=True, fill=tk.X)
            current_val = ui[entry_key].get()
            entry.insert(0, current_val if current_val else default_val)
            return entry

        x_entry = create_row("X 偏移:", "overlay_offset_x_entry", "-200")
        y_entry = create_row("Y 偏移:", "overlay_offset_y_entry", "60")
        font_entry = create_row("字型大小:", "overlay_font_size_entry", "16")
        alpha_entry = create_row("透明度 (0.1-1.0):", "overlay_alpha_entry", "0.7")
        rows_entry = create_row("最大顯示行數:", "overlay_max_rows_entry", "7")
        width_entry = create_row("固定寬度 (0=自動):", "overlay_width_entry", "0")

        def save():
            ui["overlay_offset_x_entry"].delete(0, tk.END); ui["overlay_offset_x_entry"].insert(0, x_entry.get())
            ui["overlay_offset_y_entry"].delete(0, tk.END); ui["overlay_offset_y_entry"].insert(0, y_entry.get())
            ui["overlay_font_size_entry"].delete(0, tk.END); ui["overlay_font_size_entry"].insert(0, font_entry.get())
            ui["overlay_alpha_entry"].delete(0, tk.END); ui["overlay_alpha_entry"].insert(0, alpha_entry.get())
            ui["overlay_max_rows_entry"].delete(0, tk.END); ui["overlay_max_rows_entry"].insert(0, rows_entry.get())
            ui["overlay_width_entry"].delete(0, tk.END); ui["overlay_width_entry"].insert(0, width_entry.get())
            
            # 如果 Overlay 正在執行，嘗試即時更新屬性 (除了偏移量需要重啟或複雜處理，這裡至少更新文字相關)
            if instance.get("overlay"):
                try:
                    instance["overlay"].offset_x = int(x_entry.get())
                    instance["overlay"].offset_y = int(y_entry.get())
                except: pass

            self.save_config()
            dialog.destroy()

        ttk.Button(frame, text="儲存", command=save, style='Taller.TButton').pack(pady=(10, 0), fill=tk.X)

    def open_overlay_target_list_dialog(self, name):
        """編輯 Overlay 專用目標列表的對話框"""
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 編輯 Overlay 目標")
        dialog.transient(self.root)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)

        ttk.Label(main_frame, text="請輸入 Overlay 要顯示的目標名稱，每行一個:").pack(anchor='w', pady=(0, 5))

        # --- Search Frame ---
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=5)
        
        search_label = ttk.Label(search_frame, text="搜尋:")
        search_label.pack(side=tk.LEFT, padx=(0, 5))
        
        search_entry = ttk.Entry(search_frame)
        search_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

        dialog_text_area = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD)
        dialog_text_area.pack(expand=True, fill=tk.BOTH)
        
        search_button = ttk.Button(search_frame, text="尋找", style='Taller.TButton', 
                                   command=lambda: self.search_in_text_widget(dialog_text_area, search_entry))
        search_button.pack(side=tk.LEFT)
        
        dialog_text_area.tag_configure("found", background="yellow", foreground="black")
        dialog_text_area.tag_configure("duplicate", background="orange", foreground="black")

        current_targets = ui["overlay_target_entry"].get("1.0", tk.END).strip()
        dialog_text_area.insert("1.0", current_targets)

        def save_and_close():
            new_targets = dialog_text_area.get("1.0", tk.END).strip()
            ui["overlay_target_entry"].delete("1.0", tk.END)
            ui["overlay_target_entry"].insert("1.0", new_targets)
            
            self.log_message(f"[{name}] 已更新 Overlay 目標列表。")
            dialog.destroy()

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        format_button = ttk.Button(button_frame, text="切換格式",
                                   command=lambda: self.toggle_target_format(dialog_text_area),
                                   style='Taller.TButton')
        format_button.pack(side=tk.LEFT, padx=(0, 5))

        check_button = ttk.Button(button_frame, text="檢查重複", 
                                  command=lambda: self.check_for_duplicates(dialog_text_area), 
                                  style='Taller.TButton')
        check_button.pack(side=tk.LEFT, padx=5)

        ok_button = ttk.Button(button_frame, text="儲存並關閉", command=save_and_close, style='Taller.TButton')
        ok_button.pack(side=tk.RIGHT, padx=5)
        cancel_button = ttk.Button(button_frame, text="取消", command=dialog.destroy, style='Taller.TButton')
        cancel_button.pack(side=tk.RIGHT)

        # Center the dialog
        dialog.resizable(False, False)
        dialog.update_idletasks()
        dialog_width = 500
        dialog_height = 500
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)

    def search_in_text_widget(self, text_widget, search_entry):
        query = search_entry.get()
        text_widget.tag_remove("found", "1.0", tk.END)
        if not query:
            return

        start_pos = "1.0"
        count_var = tk.IntVar()
        found_count = 0
        while True:
            pos = text_widget.search(query, start_pos, stopindex=tk.END, nocase=True, count=count_var)
            if not pos:
                break
            
            end_pos = f"{pos}+{count_var.get()}c"
            text_widget.tag_add("found", pos, end_pos)
            
            start_pos = end_pos
            found_count += 1
        
        if found_count == 0:
            messagebox.showinfo("未找到", f"在文本中找不到 '{query}'", parent=text_widget.master)

    def check_for_duplicates(self, text_widget):
        from collections import Counter
        text_widget.tag_remove("duplicate", "1.0", tk.END)

        raw_targets = text_widget.get("1.0", tk.END).strip()
        if not raw_targets:
            messagebox.showinfo("結果", "目標列表為空。", parent=text_widget.master)
            return

        target_list = [t.strip() for t in raw_targets.replace("\n", ",").split(',') if t.strip()]

        counts = Counter(target_list)
        duplicates = [item for item, count in counts.items() if count > 1]

        if not duplicates:
            messagebox.showinfo("檢查完畢", "沒有發現重複的目標。", parent=text_widget.master)
            return

        # Highlight duplicates first, so the user can see them
        for item in duplicates:
            start_pos = "1.0"
            while True:
                pos = text_widget.search(item, start_pos, stopindex=tk.END, exact=True)
                if not pos:
                    break
                end_pos = f"{pos}+{len(item)}c"
                text_widget.tag_add("duplicate", pos, end_pos)
                start_pos = end_pos

        # Now, ask the user if they want to remove them
        message = "發現重複的目標：\n\n" + "\n".join(duplicates) + "\n\n是否要自動移除重複項目，只保留一個？"
        
        if messagebox.askyesno("發現重複", message, parent=text_widget.master):
            # User clicked "Yes"
            seen = set()
            unique_list = []
            for item in target_list:
                if item not in seen:
                    seen.add(item)
                    unique_list.append(item)
            
            new_text = "\n".join(unique_list)
            text_widget.delete("1.0", tk.END)
            text_widget.insert("1.0", new_text)
            messagebox.showinfo("完成", "已自動移除重複的目標。", parent=text_widget.master)

    def toggle_target_format(self, text_widget):
        raw_targets = text_widget.get("1.0", tk.END).strip()
        if not raw_targets:
            return

        # Get a clean list of targets, handling mixed separators
        target_list = [t.strip() for t in raw_targets.replace("\n", ",").split(',') if t.strip()]
        
        # Decide which format to switch to.
        # If there are newlines in the original text, assume we want to convert to a single line of commas.
        # Otherwise, convert to a multi-line format.
        if "\n" in raw_targets:
            new_text = ",".join(target_list)
        else:
            new_text = "\n".join(target_list)
            
        # Update the text widget
        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", new_text)

    def start_parameter_search_thread(self, name, dialog_entries):
        if getattr(self, "is_searching_params", False):
            self.log_message("[自動搜尋] 另一個搜尋任務正在執行中，請稍候。")
            messagebox.showwarning("任務執行中", "另一個搜尋任務正在執行中，請稍候。")
            return

        if not messagebox.askyesno("確認", "此功能需要 JADX 工具 (jadx.bat) 且過程可能需要數分鐘。\n\n您確定要開始嗎？"):
            return

        self.is_searching_params = True
        # 可以在此處禁用按鈕
        threading.Thread(target=self._execute_parameter_search, args=(name, dialog_entries), daemon=True).start()

    def _execute_parameter_search(self, name, dialog_entries):
        try:
            script_dir = self._get_base_path()
            output_dir = os.path.join(script_dir, "output")
            out_java_dir = os.path.join(script_dir, "out_java")
            sources_dir = os.path.join(output_dir, "sources")

            if not self._run_jadx_decompilation(script_dir, output_dir):
                self.log_message("[自動搜尋] JADX 反編譯失敗或被取消，任務中止。")
                return

            if not self._prepare_source_files(sources_dir, out_java_dir):
                self.log_message("[自動搜尋] 準備來源檔案失敗，任務中止。")
                return

            results = self._find_all_parameters(out_java_dir)
            if results is None:
                self.log_message("[自動搜尋] 分析檔案失敗，找不到任何參數。")
                self.root.after(0, lambda: messagebox.showerror("分析失敗", "分析檔案失敗，找不到任何參數。\n請檢查 JADX 是否有錯誤訊息。"))
                return
            
            # --- 將結果填入 UI ---
            self.root.after(0, self._update_advanced_parameters, results, dialog_entries)

        except Exception as e:
            self.log_message(f"[自動搜尋] 發生未預期的嚴重錯誤: {e}")
            self.root.after(0, lambda: messagebox.showerror("嚴重錯誤", f"執行參數搜尋時發生錯誤:\n\n{e}"))
        finally:
            self.is_searching_params = False
            # 可以在此處重新啟用按鈕

    def _update_advanced_parameters(self, results, dialog_entries):
        self.log_message("[自動搜尋] ✅ 搜尋成功！正在將結果填入所有分頁的進階參數中...")
        self.log_message(f"[自動搜尋] 接收到的結果: {results}")
        
        # Safely get parameters
        c0391_class = results.get('201', '')
        socket_method = results.get('s', {}).get('special_char', '')
        moveto_class = results.get('g', {}).get('402', [''])[0]
        useitem_method = results.get('g', {}).get('404', [''])[0]
        auto_method = results.get('g', {}).get('403', [''])[0]
        skilluse_method = results.get('g', {}).get('409', [''])[0]
        target_method = results.get('g', {}).get('418', [''])[0]
        attack_pickup_method = results.get('g', {}).get('428', [''])[0]

        self.log_message(f"[自動搜尋] 提取的參數: c0391={c0391_class}, socket={socket_method}, moveto={moveto_class}, useitem={useitem_method}, auto={auto_method}, skilluse={skilluse_method}, target={target_method}, attack_pickup={attack_pickup_method}")

        # Update main UI entries (which are the source for the dialog when it opens)
        for instance_name, instance_data in self.instances.items():
            ui = instance_data["ui"]
            
            if c0391_class and '❌' not in c0391_class:
                ui["c0391_class_name_entry"].delete(0, tk.END)
                ui["c0391_class_name_entry"].insert(0, c0391_class)
                self.log_message(f"[自動搜尋] 更新 {instance_name} 的 c0391_class_name_entry 為 {c0391_class}")
            if socket_method and '❌' not in socket_method:
                ui["socket_utils_method_entry"].delete(0, tk.END)
                ui["socket_utils_method_entry"].insert(0, socket_method)
                self.log_message(f"[自動搜尋] 更新 {instance_name} 的 socket_utils_method_entry 為 {socket_method}")
            if moveto_class and '❌' not in moveto_class:
                ui["moveto_classname_entry"].delete(0, tk.END)
                ui["moveto_classname_entry"].insert(0, moveto_class)
                self.log_message(f"[自動搜尋] 更新 {instance_name} 的 moveto_classname_entry 為 {moveto_class}")
            if useitem_method and '❌' not in useitem_method:
                ui["use_item_method_name_entry"].delete(0, tk.END)
                ui["use_item_method_name_entry"].insert(0, useitem_method)
                self.log_message(f"[自動搜尋] 更新 {instance_name} 的 use_item_method_name_entry 為 {useitem_method}")
            if auto_method and '❌' not in auto_method:
                ui["auto_method_entry"].delete(0, tk.END)
                ui["auto_method_entry"].insert(0, auto_method)
                self.log_message(f"[自動搜尋] 更新 {instance_name} 的 auto_method_entry 為 {auto_method}")
            if skilluse_method and '❌' not in skilluse_method:
                ui["skill_use_method_name_entry"].delete(0, tk.END)
                ui["skill_use_method_name_entry"].insert(0, skilluse_method)
                self.log_message(f"[自動搜尋] 更新 {instance_name} 的 skill_use_method_name_entry 為 {skilluse_method}")
            if target_method and '❌' not in target_method:
                ui["target_method_name_entry"].delete(0, tk.END)
                ui["target_method_name_entry"].insert(0, target_method)
                self.log_message(f"[自動搜尋] 更新 {instance_name} 的 target_method_name_entry 為 {target_method}")
            if attack_pickup_method and '❌' not in attack_pickup_method:
                ui["attack_pickup_method_name_entry"].delete(0, tk.END)
                ui["attack_pickup_method_name_entry"].insert(0, attack_pickup_method)
                self.log_message(f"[自動搜尋] 更新 {instance_name} 的 attack_pickup_method_name_entry 為 {attack_pickup_method}")
        
        # Now update the dialog's entries
        if c0391_class and '❌' not in c0391_class:
            dialog_entries["c0391"].delete(0, tk.END)
            dialog_entries["c0391"].insert(0, c0391_class)
        if socket_method and '❌' not in socket_method:
            dialog_entries["socket"].delete(0, tk.END)
            dialog_entries["socket"].insert(0, socket_method)
        if moveto_class and '❌' not in moveto_class:
            dialog_entries["moveto"].delete(0, tk.END)
            dialog_entries["moveto"].insert(0, moveto_class)
        if useitem_method and '❌' not in useitem_method:
            dialog_entries["useitem"].delete(0, tk.END)
            dialog_entries["useitem"].insert(0, useitem_method)
        if auto_method and '❌' not in auto_method:
            dialog_entries["auto"].delete(0, tk.END)
            dialog_entries["auto"].insert(0, auto_method)
        if skilluse_method and '❌' not in skilluse_method:
            dialog_entries["skilluse"].delete(0, tk.END)
            dialog_entries["skilluse"].insert(0, skilluse_method)
        if target_method and '❌' not in target_method:
            dialog_entries["target"].delete(0, tk.END)
            dialog_entries["target"].insert(0, target_method)
        if attack_pickup_method and '❌' not in attack_pickup_method:
            dialog_entries["attack_pickup"].delete(0, tk.END)
            dialog_entries["attack_pickup"].insert(0, attack_pickup_method)

        self.log_message("[自動搜尋] 參數已全部填入。")
        messagebox.showinfo("搜尋成功", "參數已自動填入「進階參數設定」視窗。\n\n請檢查數值是否正確，然後點擊「儲存並關閉」。")

    def _get_base_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            # 在非打包模式下，我們假設此 gui.py 檔案位於專案根目錄
            return os.path.dirname(os.path.abspath(__file__))

    def _run_jadx_decompilation(self, script_dir, output_dir):
        self.log_message("--- [階段 0/4] JADX 反編譯 ---")
        
        # TODO: 讓 JADX 路徑可設定
        jadx_path = "C:\\Users\\small\\Desktop\\ZZ\\jadx-1.5.3\\bin\\jadx.bat"
        if not os.path.exists(jadx_path):
            self.log_message(f"[錯誤] 找不到 jadx.bat，預期路徑: {jadx_path}")
            self.root.after(0, lambda: messagebox.showerror("JADX 錯誤", f"在腳本目錄中找不到 jadx.bat。\n預期路徑: {jadx_path}"))
            return False

        if os.path.exists(output_dir):
            if messagebox.askyesno("確認", "偵測到現有的 'output' 資料夾。\n您想跳過反編譯，直接分析現有檔案嗎？"):
                self.log_message("✅ 已選擇跳過反編譯，使用現有檔案。")
                return True
            else:
                if messagebox.askyesno("警告", "即將刪除現有的 'output' 資料夾並重新反編譯。\n此過程可能需要很長時間，確定要繼續嗎？"):
                    self.log_message("正在刪除舊的 output 資料夾...")
                    try:
                        shutil.rmtree(output_dir)
                        self.log_message("✅ 舊資料夾已刪除。")
                    except Exception as e:
                        self.log_message(f"[錯誤] 刪除舊的 output 資料夾失敗: {e}")
                        self.root.after(0, lambda: messagebox.showerror("刪除失敗", f"刪除舊的 output 資料夾失敗: {e}"))
                        return False
                else:
                    return False

        apk_path = filedialog.askopenfilename(
            parent=self.root,
            initialdir=script_dir,
            title="請選擇要分析的 APK 檔案",
            filetypes=(("APK files", "*.apk"), ("All files", "*.*"))
        )

        if not apk_path:
            self.log_message("❌ 未選擇任何 APK 檔案，程式中止。")
            return False

        self.log_message(f"➡️ 已選擇 APK: {apk_path}")
        self.log_message(f"➡️ JADX 路徑: {jadx_path}")
        self.log_message(f"➡️ 輸出目錄: {output_dir}")

        command = [jadx_path, "-d", output_dir, apk_path]
        command_string_for_display = ' '.join(f'"{arg}"' for arg in command)
        self.log_message(f"\n✨ 將執行的指令:\n{command_string_for_display}\n")
        self.log_message("⏳ JADX 正在執行反編譯，此過程可能需要幾分鐘，請耐心等候...")

        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                       text=True, encoding='utf-8', errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW)

            self.log_message("--- JADX 輸出開始 ---")
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if not line: continue
                self.log_message(line)
            self.log_message("--- JADX 輸出結束 ---")

            process.wait()
            if process.returncode == 0:
                self.log_message("\n✅ JADX 反編譯成功完成！")
            else:
                self.log_message(f"\n⚠️ JADX 執行完成但回報了錯誤 (返回碼: {process.returncode})。將無視錯誤並繼續嘗試分析...")
            
            return True
        except Exception as e:
            self.log_message(f"[錯誤] 執行 JADX 時發生錯誤: {e}")
            self.root.after(0, lambda: messagebox.showerror("JADX 執行錯誤", f"執行 JADX 時發生錯誤: {e}"))
            return False

    def _prepare_source_files(self, sources_dir, out_java_dir):
        self.log_message("\n--- [階段 1/4] 準備來源檔案 ---")
        if not os.path.exists(out_java_dir):
            os.makedirs(out_java_dir)
        
        FILE_GAME_HELPER = "GameHelper.java"
        FILE_SOCKET_UTILS = "SocketUtils.java"
        
        game_helper_source_path = os.path.join(sources_dir, "com", "lineagem", "botv3", "plugin", FILE_GAME_HELPER)
        socket_utils_source_path = os.path.join(sources_dir, "com", "lineagem", "botv3", "util", FILE_SOCKET_UTILS)
        
        for name, path in {FILE_GAME_HELPER: game_helper_source_path, FILE_SOCKET_UTILS: socket_utils_source_path}.items():
            if os.path.exists(path):
                shutil.copy(path, out_java_dir)
            else:
                self.log_message(f"[錯誤] 在 output/sources 中找不到檔案: {path}")
                self.root.after(0, lambda: messagebox.showerror("檔案錯誤", f"在 output/sources 中找不到檔案: {path}"))
                return False

        try:
            with open(game_helper_source_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            self.log_message(f"[錯誤] 讀取 {FILE_GAME_HELPER} 失敗: {e}")
            self.root.after(0, lambda: messagebox.showerror("檔案讀取錯誤", f"讀取 {FILE_GAME_HELPER} 失敗: {e}"))
            return False

        match = re.search(r'new (C\d+)\(201\b', content)
        if not match: return True

        class_name, file_to_find = match.group(1), f"{match.group(1)}.java"
        for root, _, files in os.walk(sources_dir):
            if file_to_find in files:
                shutil.copy(os.path.join(root, file_to_find), out_java_dir)
                break
        self.log_message("✅ 檔案準備完成。")
        return True

    def _find_all_parameters(self, out_java_dir):
        self.log_message("\n--- [階段 2/4] 分析檔案並提取參數 ---")
        results = {'s': {}, 'g': {}, '201': None}
        FILE_GAME_HELPER = "GameHelper.java"
        FILE_SOCKET_UTILS = "SocketUtils.java"

        socket_path = os.path.join(out_java_dir, FILE_SOCKET_UTILS)
        if os.path.exists(socket_path):
            with open(socket_path, 'r', encoding='utf-8') as f: content = f.read()
            match = re.search(r'/\* renamed from: (\s*\S+?\s*), reason: contains not printable characters \*/\s*public static String (\S+)\s*\(int i, Object obj\)', content)
            if match: results['s']["special_char"], results['s']["method_name"] = match.group(1).strip(), match.group(2).strip()

        helper_path = os.path.join(out_java_dir, FILE_GAME_HELPER)
        if os.path.exists(helper_path):
            with open(helper_path, 'r', encoding='utf-8') as f: content = f.read()
            commands_to_find = {"402": "MoveTo Classname", "404": "UseItem Method", "403": "Auto指令", "409": "SkillUse Method", "418": "指定目標 Method", "428": "攻擊或撿取 Method"}
            blocks = re.split(r'/\* renamed from: ', content)
            for block in blocks[1:]:
                char_match = re.match(r'([\s\S]+?), reason:', block)
                if not char_match: continue
                full_path_string = char_match.group(1).strip()
                path_char_match = re.search(r'\$(\S+)$', full_path_string)
                special_char = path_char_match.group(1).strip() if path_char_match else full_path_string
                for cmd, desc in commands_to_find.items():
                    if cmd not in results['g'] and re.search(r'new C\d+\(' + re.escape(cmd) + r'.*?\);', block):
                        results['g'][cmd] = (special_char, desc)
                        results['g'][cmd] = (special_char, desc)
                        results['g'][cmd] = (special_char, desc)

            match_201 = re.search(r'new (C\d+)\(201\b', content)
            if match_201:
                class_name_201 = f"{match_201.group(1)}.java"
                path_201 = os.path.join(out_java_dir, class_name_201)
                if os.path.exists(path_201):
                    with open(path_201, 'r', encoding='utf-8') as f_201: header = f_201.read(4096)
                    original_name_match = re.search(r'/\* renamed from: (.*?),\s*reason: contains not printable characters \*/', header)
                    results['201'] = original_name_match.group(1).strip() if original_name_match else f"⚠️ 在 {class_name_201} 中找不到註解"
                else: results['201'] = f"⚠️ 找不到 {class_name_201} 檔案"
            else: results['201'] = "⚠️ 在 GameHelper 中找不到 201 指令"

        self.log_message("✅ 分析完成！")
        return results

    def open_coord_monitor_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 監控座標設定")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)

        # --- Main settings ---
        settings_frame = ttk.Frame(main_frame)
        settings_frame.pack(fill=tk.X)
        
        pos_check = ttk.Checkbutton(settings_frame, text="啟用座標監控", variable=ui["monitor_pos_var"])
        pos_check.pack(anchor='w', pady=(0, 10))

        pos_frame = ttk.LabelFrame(settings_frame, text="目標座標", padding="10")
        pos_frame.pack(fill=tk.X)
        
        ttk.Label(pos_frame, text="X:").pack(side=tk.LEFT)
        monitor_x_entry = ttk.Entry(pos_frame, width=8)
        monitor_x_entry.pack(side=tk.LEFT, padx=(2, 8))
        monitor_x_entry.insert(0, ui["monitor_x_entry"].get())

        ttk.Label(pos_frame, text="Y:").pack(side=tk.LEFT)
        monitor_y_entry = ttk.Entry(pos_frame, width=8)
        monitor_y_entry.pack(side=tk.LEFT, padx=(2, 8))
        monitor_y_entry.insert(0, ui["monitor_y_entry"].get())

        get_pos_button = ttk.Button(pos_frame, text="讀取當前座標", style='Taller.TButton')
        get_pos_button.pack(side=tk.LEFT, padx=5)
        get_pos_button['command'] = lambda: self.get_current_position_thread(name, monitor_x_entry, monitor_y_entry, get_pos_button)

        # --- Details ---
        details_frame = ttk.LabelFrame(settings_frame, text="判斷條件", padding="10")
        details_frame.pack(fill=tk.X, pady=(10, 0))
        details_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(details_frame, text="超出範圍(格):").grid(row=0, column=0, sticky="w", pady=2)
        monitor_range_entry = ttk.Entry(details_frame, width=10)
        monitor_range_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        monitor_range_entry.insert(0, ui["monitor_range_entry"].get())

        ttk.Label(details_frame, text="檢查間隔(秒):").grid(row=1, column=0, sticky="w", pady=2)
        pos_interval_entry = ttk.Entry(details_frame, width=10)
        pos_interval_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        pos_interval_entry.insert(0, ui["pos_interval_entry"].get())

        # --- Buttons ---
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))

        def save_and_close():
            # Save values back to the hidden main UI entries
            ui["monitor_x_entry"].delete(0, tk.END)
            ui["monitor_x_entry"].insert(0, monitor_x_entry.get())
            ui["monitor_y_entry"].delete(0, tk.END)
            ui["monitor_y_entry"].insert(0, monitor_y_entry.get())
            ui["monitor_range_entry"].delete(0, tk.END)
            ui["monitor_range_entry"].insert(0, monitor_range_entry.get())
            ui["pos_interval_entry"].delete(0, tk.END)
            ui["pos_interval_entry"].insert(0, pos_interval_entry.get())
            # The Checkbutton variable (monitor_pos_var) is updated automatically
            self.log_message(f"[{name}] 已更新座標監控設定。")

        ok_button = ttk.Button(button_frame, text="儲存", command=save_and_close, style='Taller.TButton')
        ok_button.pack(side=tk.RIGHT)
        cancel_button = ttk.Button(button_frame, text="取消", command=dialog.destroy, style='Taller.TButton')
        cancel_button.pack(side=tk.RIGHT, padx=(0, 5))

        # --- Center dialog ---
        dialog.update_idletasks()
        dialog_width = 320
        dialog_height = 280
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)



    def open_advanced_params_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 進階參數設定")
        dialog.resizable(False, False)
        dialog.transient(self.root)

        self.root.update_idletasks()
        dialog_width, dialog_height = 350, 360
        main_win_x, main_win_y = self.root.winfo_x(), self.root.winfo_y()
        main_win_width, main_win_height = self.root.winfo_width(), self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)
        grid_frame = ttk.Frame(main_frame)
        grid_frame.pack(expand=True, fill=tk.BOTH)
        grid_frame.grid_columnconfigure(1, weight=1)

        dialog_entries = {}
        params = [
            ("C0391 Class:", "c0391", "c0391_class_name_entry"),
            ("SocketUtils Method:", "socket", "socket_utils_method_entry"),
            ("MoveTo Classname:", "moveto", "moveto_classname_entry"),
            ("UseItem Method:", "useitem", "use_item_method_name_entry"),
            ("Auto Method:", "auto", "auto_method_entry"),
            ("SkillUse Method:", "skilluse", "skill_use_method_name_entry"),
            ("指定目標 Method:", "target", "target_method_name_entry"),
            ("攻擊或撿取 Method:", "attack_pickup", "attack_pickup_method_name_entry")
        ]
        for i, (text, key, ui_key) in enumerate(params):
            ttk.Label(grid_frame, text=text).grid(row=i, column=0, sticky="w", padx=(0, 5), pady=5)
            entry = ttk.Entry(grid_frame)
            entry.grid(row=i, column=1, sticky="ew")
            entry.insert(0, ui[ui_key].get())
            dialog_entries[key] = entry

        def save_and_close():
            new_values = {key: entry.get() for key, entry in dialog_entries.items()}
            for instance_name, instance_data in self.instances.items():
                instance_ui = instance_data["ui"]
                instance_ui["c0391_class_name_entry"].delete(0, tk.END); instance_ui["c0391_class_name_entry"].insert(0, new_values["c0391"])
                instance_ui["socket_utils_method_entry"].delete(0, tk.END); instance_ui["socket_utils_method_entry"].insert(0, new_values["socket"])
                instance_ui["moveto_classname_entry"].delete(0, tk.END); instance_ui["moveto_classname_entry"].insert(0, new_values["moveto"])
                instance_ui["use_item_method_name_entry"].delete(0, tk.END); instance_ui["use_item_method_name_entry"].insert(0, new_values["useitem"])
                instance_ui["auto_method_entry"].delete(0, tk.END); instance_ui["auto_method_entry"].insert(0, new_values["auto"])
                instance_ui["skill_use_method_name_entry"].delete(0, tk.END); instance_ui["skill_use_method_name_entry"].insert(0, new_values["skilluse"])
                instance_ui["target_method_name_entry"].delete(0, tk.END); instance_ui["target_method_name_entry"].insert(0, new_values["target"])
                instance_ui["attack_pickup_method_name_entry"].delete(0, tk.END); instance_ui["attack_pickup_method_name_entry"].insert(0, new_values["attack_pickup"])
            self.log_message(f"[{name}] 已更新共用進階參數，並同步至所有分頁。")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        # Frame for the "參數取得說明" button
        param_info_button_frame = ttk.Frame(button_frame)
        param_info_button_frame.pack(fill=tk.X, pady=(0, 5))
        param_info_button = ttk.Button(param_info_button_frame, text="參數取得說明", command=lambda: self.show_parameter_info(name))
        param_info_button.pack(fill=tk.X)

        # Frame for other buttons
        other_buttons_frame = ttk.Frame(button_frame)
        other_buttons_frame.pack(fill=tk.X)

        search_button = ttk.Button(other_buttons_frame, text="自動搜尋參數", command=lambda: self.start_parameter_search_thread(name, dialog_entries))
        search_button.pack(side=tk.LEFT, padx=5)

        ok_button = ttk.Button(other_buttons_frame, text="儲存並關閉", command=save_and_close)
        ok_button.pack(side=tk.RIGHT, padx=5)
        cancel_button = ttk.Button(other_buttons_frame, text="取消", command=dialog.destroy)
        cancel_button.pack(side=tk.RIGHT)
        self.root.wait_window(dialog)

    def open_coords_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 座標預設")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        scrollable_frame = ttk.Frame(main_frame)
        scrollable_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollable_frame.grid_columnconfigure(0, weight=0)
        scrollable_frame.grid_columnconfigure(2, weight=0)
        scrollable_frame.grid_columnconfigure(4, weight=0)
        scrollable_frame.grid_columnconfigure(5, weight=0)
        scrollable_frame.grid_columnconfigure(6, weight=0)

        dialog_entries = []

        def _create_mover(x_entry, y_entry):
            def _move():
                ui = self.instances[name]["ui"]
                x_val, y_val = x_entry.get(), y_entry.get()
                ui["x_entry"].delete(0, tk.END); ui["x_entry"].insert(0, x_val)
                ui["y_entry"].delete(0, tk.END); ui["y_entry"].insert(0, y_val)
                self.run_moveto_thread(name)
            return _move

        for i in range(10):
            scrollable_frame.grid_rowconfigure(i, pad=7)
            name_entry = ttk.Entry(scrollable_frame, width=10)
            name_entry.grid(row=i, column=0, sticky="ew", padx=(0, 10))
            name_entry.insert(0, ui["coord_presets_entries"][i]["name"].get())
            ttk.Label(scrollable_frame, text="X:").grid(row=i, column=1, sticky="w")
            x_entry = ttk.Entry(scrollable_frame, width=7)
            x_entry.grid(row=i, column=2, sticky="ew", padx=(2, 10))
            x_entry.insert(0, ui["coord_presets_entries"][i]["x"].get())
            ttk.Label(scrollable_frame, text="Y:").grid(row=i, column=3, sticky="w")
            y_entry = ttk.Entry(scrollable_frame, width=7)
            y_entry.grid(row=i, column=4, sticky="ew", padx=(2, 10))
            y_entry.insert(0, ui["coord_presets_entries"][i]["y"].get())
            dialog_entries.append({"name": name_entry, "x": x_entry, "y": y_entry})
            move_button = ttk.Button(scrollable_frame, text="移動", command=_create_mover(x_entry, y_entry), style='Taller.TButton')
            move_button.grid(row=i, column=5, sticky="ew", padx=(0, 5))
            get_coords_button = ttk.Button(scrollable_frame, text="讀取", style='Taller.TButton' , width=7)
            get_coords_button['command'] = lambda x_e=x_entry, y_e=y_entry, btn=get_coords_button: self.get_coords_for_preset_row_thread(name, x_e, y_e, btn)
            get_coords_button.grid(row=i, column=6, sticky="ew")

        def save_and_close():
            for i in range(10):
                preset_entry_group = ui["coord_presets_entries"][i]
                dialog_entry_group = dialog_entries[i]
                preset_entry_group["name"].delete(0, tk.END); preset_entry_group["name"].insert(0, dialog_entry_group["name"].get())
                preset_entry_group["x"].delete(0, tk.END); preset_entry_group["x"].insert(0, dialog_entry_group["x"].get())
                preset_entry_group["y"].delete(0, tk.END); preset_entry_group["y"].insert(0, dialog_entry_group["y"].get())
            self.log_message(f"[{name}] 已儲存座標預設。")

        ok_button = ttk.Button(button_frame, text="儲存", command=save_and_close, style='Taller.TButton')
        ok_button.pack(side=tk.RIGHT, padx=5)
        cancel_button = ttk.Button(button_frame, text="取消", command=dialog.destroy, style='Taller.TButton')
        cancel_button.pack(side=tk.RIGHT)

        dialog.update_idletasks()
        dialog_width, dialog_height = 418, 350
        main_win_x, main_win_y = self.root.winfo_x(), self.root.winfo_y()
        main_win_width, main_win_height = self.root.winfo_width(), self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")
        self.root.wait_window(dialog)

    def get_coords_for_preset_row_thread(self, name, x_entry, y_entry, button):
        instance = self.instances[name]
        if not instance.get("script_api"):
            self.log_message(f"[{name}] 讀取座標失敗: 未連接。")
            messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接'。")
            return
        button.config(state='disabled')
        threading.Thread(target=self.execute_get_coords_for_preset, args=(name, x_entry, y_entry, button), daemon=True).start()

    def execute_get_coords_for_preset(self, name, x_entry, y_entry, button):
        instance = self.instances[name]
        api = instance["script_api"]
        try:
            self.log_message(f"[{name}] 正在為座標預設讀取當前位置...")
            player_info_str = api.get_info(201)
            if not player_info_str:
                raise Exception("獲取角色資訊失敗 (RPC get_info(201) 未返回任何資料)")

            pos_x, pos_y = None, None
            player_data = json.loads(player_info_str)
            info_dict = player_data.get('data', player_data)

            if 'x' in info_dict and 'y' in info_dict:
                pos_x, pos_y = info_dict['x'], info_dict['y']
            elif 'worldX' in info_dict and 'worldY' in info_dict:
                pos_x, pos_y = info_dict['worldX'], info_dict['worldY']

            if pos_x is not None and pos_y is not None:
                self.log_message(f"[{name}] 成功讀取座標: X={pos_x}, Y={pos_y}")
                def _update_ui():
                    x_entry.delete(0, tk.END); x_entry.insert(0, str(pos_x))
                    y_entry.delete(0, tk.END); y_entry.insert(0, str(pos_y))
                if self.root.winfo_exists(): self.root.after(0, _update_ui)
            else:
                self.log_message(f"[{name}] 錯誤: 在回傳的JSON中找不到座標欄位。")
        except Exception as e:
            self.log_message(f"[{name}] 錯誤: 讀取座標時發生錯誤: {e}")
            self.handle_script_error(e, name)
        finally:
            if self.root.winfo_exists(): self.root.after(0, lambda: button.config(state='normal'))

    def _attempt_use_back_to_village_scroll(self, name, api, item_key):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            self.log_message(f"[{name}] 正在使用 itemKey: {item_key} ...")
            result = api.use_item(str(item_key))
            self.log_message(f"[{name}] RPC use_item 返回: {result}")

            if instance.get("detection_start_time"):
                end_time = time.time()
                duration = end_time - instance["detection_start_time"]
                self.log_message(f"--- [{name}] 從偵測到目標至使用卷軸，耗時: {duration:.2f} 秒 ---")
                instance["detection_start_time"] = None # 清除計時，避免重複紀錄

            self.log_message(f"[{name}] 等待回到安全區域 (zone = 1)...")
            max_wait_time, check_interval = 0.1, 0.1
            wait_start_time = time.time()
            while time.time() - wait_start_time < max_wait_time:
                player_info_str = api.get_info(201)
                current_zone = -1
                if player_info_str:
                    try: current_zone = json.loads(player_info_str).get('zone', -1)
                    except json.JSONDecodeError: self.log_message(f"[{name}] 錯誤: 解析玩家資訊JSON失敗。")
                if current_zone == 1:
                    self.log_message(f"[{name}] 已確認回到安全區域 (zone = {current_zone})。")
                    return True
                else:
                    self.log_message(f"[{name}] 仍在非安全區域 (zone = {current_zone})，等待...")
                time.sleep(check_interval)
            self.log_message(f"[{name}] 警告: 超時未回到安全區域。目前區域: {current_zone}")
            return False
        except Exception as e:
            self.log_message(f"[{name}] 錯誤: 使用回村卷軸時發生錯誤: {e}")
            self.handle_script_error(e, name)
            return False

    def run_moveto_thread(self, name, internal_call=False):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        if not internal_call and (instance["is_monitoring"] or instance["is_seq_moving"]):
            return messagebox.showwarning(f"[{name}] 操作中", "請先停止監控或循序移動。")
        if not instance["session"] or instance["session"].is_detached:
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接'。")
        
        x_val, y_val = ui["x_entry"].get(), ui["y_entry"].get()
        if not x_val.isdigit() or not y_val.isdigit():
            return messagebox.showerror(f"[{name}] 輸入錯誤", "X 和 Y 座標必須是數字。")
        
        threading.Thread(target=self.execute_moveto_script, args=(name, int(x_val), int(y_val)), daemon=True).start()

    def execute_moveto_script(self, name, x, y):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            self.log_message(f"--- [{name}] 準備執行移動指令: X={x}, Y={y} ---")
            
            # --- Fix: Use RPC moveTo instead of creating new script ---
            api = instance.get("script_api")
            if not api:
                raise Exception("RPC 尚未就緒，無法執行移動。")

            # Note: We don't need to pass classname here anymore, it's baked into the RPC script
            # classname = ui["moveto_classname_entry"].get() 
            
            self.log_message(f"[{name}] 正在呼叫 RPC api.moveto({x}, {y})...")
            result = api.moveto(x, y)
            self.log_message(f"[{name}] RPC moveTo 回傳結果: {result}")
            # ----------------------------------------------------------

        except Exception as e:
            self.log_message(f"[{name}] RPC moveTo 發生錯誤: {e}")
            self.handle_script_error(e, name)

    def back_to_village_thread(self, name, internal_call=False):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        if not internal_call and (instance["is_monitoring"] or instance["is_seq_moving"]):
            return messagebox.showwarning(f"[{name}] 操作中", "請先停止監控或循序移動。")
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        ui["back_button"].config(state='disabled', text="處理中...")
        threading.Thread(target=self.execute_back_to_village, args=(name,), daemon=True).start()

    def execute_back_to_village(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        api = instance["script_api"]
        item_name_to_use = "傳送回家的卷軸(刻印)" # 預設

        if ui["use_forgotten_island_scroll_var"].get():
            item_name_to_use = "遺忘之傳送回家的卷軸(刻印)"
            self.log_message(f"[{name}] 已勾選使用遺忘島卷軸。")
        else:
            item_name_to_use = "傳送回家的卷軸(刻印)"

        item_key_cache = instance.setdefault("item_key_cache", {})
        item_key = item_key_cache.get(item_name_to_use)
        
        start_time = time.time()
        try:
            if not item_key:
                self.log_message(f"--- [{name}] 快取未命中，開始執行 '回村' (搜尋: {item_name_to_use}) ---")
                inventory_start_time = time.time()
                self.log_message(f"[{name}] 1/3 正在獲取背包列表...")
                inventory_json_str = api.get_info(202)
                if not inventory_json_str: raise Exception("獲取背包列表失敗 (RPC get_info(202) 未返回任何資料)")
                self.log_message(f"[{name}] 獲取背包列表耗時: {time.time() - inventory_start_time:.2f} 秒")

                find_item_start_time = time.time()
                self.log_message(f"[{name}] 2/3 成功獲取背包列表，正在尋找 '{item_name_to_use}'...")
                try:
                    inventory_data = json.loads(inventory_json_str)
                    if inventory_data.get("status") == "success":
                        for item in inventory_data.get("data", []):
                            if item.get("itemName") == item_name_to_use:
                                item_key = item.get("itemKey")
                                self.log_message(f"[{name}] 成功: 找到物品 '{item_name_to_use}' 的 itemKey: {item_key}")
                                item_key_cache[item_name_to_use] = item_key
                                self.log_message(f"[{name}] -> Key 已存入快取")
                                break
                except json.JSONDecodeError:
                    self.log_message(f"[{name}] 錯誤: 解析背包列表JSON失敗。原始資料: {inventory_json_str}")
                    return
                self.log_message(f"[{name}] 尋找物品耗時: {time.time() - find_item_start_time:.2f} 秒")
            else:
                self.log_message(f"--- [{name}] 快取命中! 開始執行 '回村' (使用快取 Key for {item_name_to_use}) ---")

            if not item_key:
                self.log_message(f"[{name}] 錯誤: 在背包中找不到 '{item_name_to_use}'。")
                self.root.after(0, lambda: messagebox.showwarning(f"[{name}] 未找到", f"在您的背包中找不到 '{item_name_to_use}'。"))
                return

            max_retries, check_interval = 100, 0.2
            for attempt in range(1, max_retries + 1):
                self.log_message(f"[{name}] 回村嘗試 {attempt}/{max_retries}...")
                if self._attempt_use_back_to_village_scroll(name, api, item_key): break
                else:
                    self.log_message(f"[{name}] 未能回到安全區域，將在 {check_interval} 秒後重試...")
                    time.sleep(check_interval)
            
            player_info_str = api.get_info(201)
            current_zone = -1
            if player_info_str:
                try: current_zone = json.loads(player_info_str).get('zone', -1)
                except json.JSONDecodeError: self.log_message(f"[{name}] 錯誤: 解析玩家資訊JSON失敗。")
            if current_zone != 1: self.log_message(f"[{name}] 警告: 經過多次嘗試後仍未回到安全區域。目前區域: {current_zone}")

            duration = time.time() - start_time
            self.log_message(f"--- [{name}] '回村' 操作完成，總耗時: {duration:.2f} 秒 ---")
        except Exception as e:
            self.log_message(f"[{name}] 錯誤: '回村' 流程發生錯誤: {e}")
            self.handle_script_error(e, name)
        finally:
            if self.root.winfo_exists(): self.root.after(0, lambda: ui["back_button"].config(state='normal', text="回村"))
    
    def use_item_thread(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        if instance["is_monitoring"] or instance["is_seq_moving"]:
            return messagebox.showwarning(f"[{name}] 操作中", "請先停止監控或循序移動。")
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        item_name = ui["item_name_entry"].get().strip()
        if not item_name:
            return messagebox.showwarning(f"[{name}] 輸入錯誤", "請在物品名稱欄位輸入要使用的物品名稱。")

        ui["use_item_button"].config(state='disabled', text="處理中...")
        threading.Thread(target=self.use_item_sequence, args=(name, item_name), daemon=True).start()

    def use_item_sequence(self, name, item_name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            self.log_message(f"--- [{name}] 開始使用物品: {item_name} ---")
            api = instance["script_api"]
            self.log_message(f"[{name}] 1/3 正在透過RPC獲取背包列表...")
            inventory_json_str = api.get_info(202)
            self.process_and_log_json(name, inventory_json_str) # Log the full inventory

            if not inventory_json_str: raise Exception("RPC get_info(202) 未返回任何資料")

            self.log_message(f"[{name}] 2/3 成功獲取背包列表，正在尋找物品...")
            item_key = None
            try:
                inventory_data = json.loads(inventory_json_str)
                if inventory_data.get("status") == "success":
                    for item in inventory_data.get("data", []):
                        if item.get("itemName") == item_name:
                            item_key = item.get("itemKey")
                            self.log_message(f"[{name}] 成功: 找到物品 '{item_name}' 的 itemKey: {item_key}")
                            break
            except json.JSONDecodeError:
                self.log_message(f"[{name}] 錯誤: 解析背包列表JSON失敗。")
                return

            if not item_key:
                self.log_message(f"[{name}] 錯誤: 在背包中找不到名稱為 '{item_name}' 的物品。")
                self.root.after(0, lambda: messagebox.showwarning(f"[{name}] 未找到", f"在您的背包中找不到 '{item_name}'。"))
                return

            self.log_message(f"[{name}] 3/3 正在透過RPC使用 itemKey: {item_key} ...")
            result = api.use_item(str(item_key))
            self.log_message(f"[{name}] RPC use_item 返回: {result}")
            self.log_message(f"--- [{name}] 完成使用物品: {item_name} ---")

        except Exception as e:
            self.log_message(f"[{name}] 錯誤: '使用物品' 流程發生未知錯誤: {e}")
            self.root.after(0, lambda: messagebox.showerror(f"[{name}] 未知錯誤", f"執行過程中發生錯誤: {e}"))
        finally:
            if self.root.winfo_exists(): self.root.after(0, lambda: ui["use_item_button"].config(state='normal', text="使用物品(即時)"))

    def use_skill_thread(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        skill_id_str = ui["skill_id_entry"].get().strip()
        target_key_str = ui["target_key_entry"].get().strip()

        if not skill_id_str.isdigit():
            return messagebox.showwarning(f"[{name}] 輸入錯誤", "技能 ID 必須是數字。")
        
        if not target_key_str:
            target_key_str = "0"

        ui["use_skill_button"].config(state='disabled', text="使用中...")
        threading.Thread(target=self.execute_use_skill, args=(name, int(skill_id_str), target_key_str), daemon=True).start()


    def execute_use_skill(self, name, skill_id, target_key, update_ui=True):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            self.log_message(f"--- [{name}] 開始使用技能 ID: {skill_id}, 目標 Key: {target_key} ---")
            api = instance["script_api"]
            result = api.use_skill(skill_id, target_key)
            self.log_message(f"[{name}] RPC use_skill 返回: {result}")
            self.log_message(f"--- [{name}] 完成使用技能 ---")

        except Exception as e:
            self.log_message(f"[{name}] 錯誤: '使用技能' 流程發生未知錯誤: {e}")
            self.handle_script_error(e, name)
        finally:
            if update_ui and self.root.winfo_exists():
                self.root.after(0, lambda: ui["use_skill_button"].config(state='normal', text="使用技能"))

    def select_nearby_player_thread(self, name):
        """選擇周圍玩家並填入 targetKey 欄位"""
        instance = self.instances[name]
        ui = instance.get("ui")
        
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")
        
        # 禁用按鈕
        if ui["select_player_button"].winfo_exists():
            ui["select_player_button"].config(state='disabled', text="讀取中...")
        
        threading.Thread(target=self._execute_select_nearby_player, args=(name,), daemon=True).start()

    def _execute_select_nearby_player(self, name):
        """執行選擇周圍玩家的流程"""
        instance = self.instances[name]
        ui = instance.get("ui")
        api = instance.get("script_api")
        
        try:
            # 獲取周圍物件
            objects_data = self._get_surrounding_objects(name)
            
            if not objects_data:
                messagebox.showinfo(f"[{name}] 無物件", "未能獲取到周圍物件資訊。")
                return
            
            # 過濾出玩家 (type == 2)
            players = [obj for obj in objects_data if obj.get("type") == 2]
            
            if not players:
                self.root.after(0, lambda: messagebox.showinfo(f"[{name}] 無玩家", "周圍沒有其他玩家。"))
                return
            
            # 在主線程中顯示選擇對話框
            if self.root.winfo_exists():
                self.root.after(0, lambda: self._show_player_selection_dialog(name, players))
        
        except Exception as e:
            self.log_message(f"[{name}] 獲取周圍玩家時發生錯誤: {e}")
            self.handle_script_error(e, name)
        finally:
            # 恢復按鈕狀態
            if self.root.winfo_exists() and ui and ui["select_player_button"].winfo_exists():
                self.root.after(0, lambda: ui["select_player_button"].config(state='normal', text="選擇玩家"))

    def _show_player_selection_dialog(self, name, players):
        """顯示玩家選擇對話框"""
        instance = self.instances[name]
        ui = instance.get("ui")
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 選擇玩家")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()
        
        selected_player = None
        
        def on_select():
            nonlocal selected_player
            selected_indices = listbox.curselection()
            if not selected_indices:
                messagebox.showwarning("未選擇", "請先在列表中選擇一個玩家。", parent=dialog)
                return
            
            selected_text = listbox.get(selected_indices[0])
            selected_player = player_map.get(selected_text)
            dialog.destroy()
        
        def on_double_click(event):
            on_select()
        
        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_rowconfigure(1, weight=1)  # 讓列表框所在的行可以擴展
        main_frame.grid_columnconfigure(0, weight=1)
        
        # 說明標籤
        info_label = ttk.Label(main_frame, text="選擇一個玩家來施放技能:")
        info_label.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        # 列表框
        listbox_frame = ttk.Frame(main_frame)
        listbox_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        listbox = Listbox(listbox_frame, selectmode=tk.SINGLE)
        listbox.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        listbox.bind("<Double-Button-1>", on_double_click)
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)
        
        # 填充玩家列表
        player_map = {}
        for player in players:
            player_name = player.get("name", "未知玩家")
            object_key = player.get("objectKey", "")
            clan_name = player.get("clanName", "")
            level = player.get("level", "")
            
            # 組合顯示文字
            display_parts = [player_name]
            if clan_name:
                display_parts.append(f"[{clan_name}]")
            if level:
                display_parts.append(f"Lv.{level}")
            display_parts.append(f"(Key: {object_key})")
            
            display_text = " ".join(display_parts)
            listbox.insert(tk.END, display_text)
            player_map[display_text] = object_key
        
        # 按鈕框架
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, sticky="ew")
        
        select_button = ttk.Button(button_frame, text="選擇", command=on_select, style='Taller.TButton')
        select_button.pack(side=tk.RIGHT, padx=(5, 0))
        cancel_button = ttk.Button(button_frame, text="取消", command=dialog.destroy, style='Taller.TButton')
        cancel_button.pack(side=tk.RIGHT)
        
        # 居中顯示對話框
        dialog.update_idletasks()
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"+{center_x}+{center_y}")
        
        self.root.wait_window(dialog)
        
        # 如果選擇了玩家，更新 targetKey 輸入欄位
        if selected_player is not None:
            if ui and ui["target_key_entry"].winfo_exists():
                ui["target_key_entry"].delete(0, tk.END)
                ui["target_key_entry"].insert(0, str(selected_player))
                self.log_message(f"[{name}] 已選擇玩家 objectKey: {selected_player}")


    def specify_closest_target_thread(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        ui["specify_target_button"].config(state='disabled', text="搜尋中...")
        threading.Thread(target=self.execute_specify_closest_target, args=(name,), daemon=True).start()


    def select_skill_thread(self, name, target_entry_widget, button_widget):
        instance = self.instances[name]
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接'。")
        
        if button_widget and button_widget.winfo_exists():
            button_widget.config(state='disabled')
        
        self.log_message(f"--- [{name}] 正在獲取技能列表... ---")
        threading.Thread(target=self._execute_select_skill_generic, args=(name, target_entry_widget, button_widget), daemon=True).start()

    def _execute_select_skill_generic(self, name, target_entry_widget, button_widget):
        # Runs in worker thread
        instance = self.instances[name]
        api = instance.get("script_api")
        if not api:
            self.log_message(f"[{name}] 獲取技能失敗: 未連接。")
            return

        try:
            skills_str = api.get_info(218)
            if not skills_str:
                raise Exception("獲取技能列表失敗 (RPC get_info(218) 未返回任何資料)")
            
            skills_data = json.loads(skills_str)
            if skills_data.get("status") != "success":
                raise Exception(f"獲取技能列表失敗: {skills_data.get('message', '未知錯誤')}")

            skills = skills_data.get("data", [])

            def _show_dialog_and_update():
                # Runs in main thread
                if not skills:
                    messagebox.showinfo(f"[{name}] 無技能", "無法獲取到任何技能。", parent=self.root)
                    return

                selected_skill_id = self._show_skill_selection_dialog_and_get_id(name, skills)

                if selected_skill_id is not None:
                    if target_entry_widget and target_entry_widget.winfo_exists():
                        target_entry_widget.delete(0, tk.END)
                        target_entry_widget.insert(0, str(selected_skill_id))
                        self.log_message(f"[{name}] 已選擇技能 ID: {selected_skill_id}")
            
            if self.root.winfo_exists():
                self.root.after(0, _show_dialog_and_update)

        except Exception as e:
            self.log_message(f"[{name}] 獲取或選擇技能時發生錯誤: {e}")
            self.handle_script_error(e, name)
        finally:
            if button_widget and button_widget.winfo_exists():
                self.root.after(0, lambda: button_widget.config(state='normal'))



    def _show_skill_selection_dialog_and_get_id(self, name, skills):
        if not skills:
            self.root.after(0, lambda: messagebox.showinfo(f"[{name}] 無技能", "未能讀取到任何技能。"))
            return None

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 選擇技能")
        dialog.geometry("350x400")
        
        selected_id = None

        def on_select():
            nonlocal selected_id
            selected_indices = listbox.curselection()
            if not selected_indices:
                messagebox.showwarning("未選擇", "請先在列表中選擇一個技能。", parent=dialog)
                return
            
            selected_text = listbox.get(selected_indices[0])
            selected_id = skill_map.get(selected_text)
            dialog.destroy()

        def on_double_click(event):
            on_select()

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        listbox_frame = ttk.Frame(main_frame)
        listbox_frame.grid(row=0, column=0, sticky="nsew")
        listbox = Listbox(listbox_frame, selectmode=tk.SINGLE)
        listbox.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        listbox.bind("<Double-Button-1>", on_double_click)
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)

        skill_map = {}
        for skill in skills:
            skill_id = skill.get("skillID")
            skill_name = skill.get("skillName", f"未知技能ID:{skill_id}")
            display_text = f"{skill_name} (ID: {skill_id})"
            listbox.insert(tk.END, display_text)
            skill_map[display_text] = skill_id

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        select_button = ttk.Button(button_frame, text="選擇", command=on_select, style='Taller.TButton')
        select_button.pack(side=tk.RIGHT)
        cancel_button = ttk.Button(button_frame, text="取消", command=dialog.destroy, style='Taller.TButton')
        cancel_button.pack(side=tk.RIGHT, padx=(0, 5))

        dialog.update_idletasks()
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"+{center_x}+{center_y}")

        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)
        
        return selected_id

    def open_specify_target_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 編輯指定目標列表")
        dialog.transient(self.root)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)

        notebook = ttk.Notebook(main_frame)
        notebook.pack(expand=True, fill=tk.BOTH)

        # Store entries for each group
        dialog_target_groups_entries = []

        for i in range(5):
            group_frame = ttk.Frame(notebook, padding="10")
            notebook.add(group_frame, text=f"目標組 {i+1}")

            group_frame.grid_columnconfigure(1, weight=1)

            ttk.Label(group_frame, text="組名:").grid(row=0, column=0, sticky="w", pady=(0, 5))
            name_entry = ttk.Entry(group_frame)
            name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 5), padx=(5,0))
            name_entry.insert(0, ui["specify_target_groups"][i]["name"])

            ttk.Label(group_frame, text="目標名稱 (每行一個):").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
            targets_text = scrolledtext.ScrolledText(group_frame, height=8, wrap=tk.WORD)
            targets_text.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 5))
            targets_text.insert("1.0", ui["specify_target_groups"][i]["targets"])
            group_frame.grid_rowconfigure(2, weight=1)

            load_surrounding_button = ttk.Button(group_frame, text="載入周圍物件 (203)", style='Taller.TButton',
                                                 command=lambda current_targets_text=targets_text: self.open_surrounding_objects_dialog(name, current_targets_text))
            load_surrounding_button.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5,0))

            dialog_target_groups_entries.append({"name_entry": name_entry, "targets_text": targets_text})

        def save_and_close():
            for i in range(5):
                ui["specify_target_groups"][i]["name"] = dialog_target_groups_entries[i]["name_entry"].get()
                ui["specify_target_groups"][i]["targets"] = dialog_target_groups_entries[i]["targets_text"].get("1.0", tk.END).strip()
            
            # Update the main UI's displayed group name and hidden targets
            selected_index = ui["specify_target_selected_group_index"].get()
            ui["specify_target_selected_group_name_var"].set(ui["specify_target_groups"][selected_index]["name"])
            
            # Update combobox values in main UI
            new_combobox_values = [group["name"] for group in ui["specify_target_groups"]]
            ui["specify_target_group_combobox"]['values'] = new_combobox_values
            ui["specify_target_group_combobox"].set(ui["specify_target_groups"][selected_index]["name"])

            ui["specify_target_current_targets_text"].config(state='normal')
            ui["specify_target_current_targets_text"].delete("1.0", tk.END)
            ui["specify_target_current_targets_text"].insert("1.0", ui["specify_target_groups"][selected_index]["targets"])
            ui["specify_target_current_targets_text"].config(state='disabled')

            self.log_message(f"[{name}] 已更新指定目標列表。")
            self.save_config() # Immediately persist changes to config.json

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ok_button = ttk.Button(button_frame, text="儲存", command=save_and_close, style='Taller.TButton')
        ok_button.pack(side=tk.RIGHT, padx=5)
        cancel_button = ttk.Button(button_frame, text="取消", command=dialog.destroy, style='Taller.TButton')
        cancel_button.pack(side=tk.RIGHT)

        # Center dialog
        dialog.update_idletasks()
        dialog_width = 450
        dialog_height = 400
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)

    def open_surrounding_objects_dialog(self, name, targets_text_widget):
        instance = self.instances[name]
        if not instance.get("script_api"):
            messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 選擇周圍物件")
        dialog.transient(self.root)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)

        # Fetch surrounding objects
        objects_data = self._get_surrounding_objects(name) # A new helper function to fetch and parse 203 data

        if not objects_data:
            messagebox.showinfo(f"[{name}] 無物件", "未能獲取到周圍物件資訊。")
            dialog.destroy()
            return

        # Create a listbox to display objects
        listbox_frame = ttk.Frame(main_frame)
        listbox_frame.pack(expand=True, fill=tk.BOTH)

        object_listbox = Listbox(listbox_frame, selectmode=tk.MULTIPLE)
        object_listbox.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=object_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        object_listbox.config(yscrollcommand=scrollbar.set)

        # Populate listbox with objects
        # Store object data (name, type) for later use
        display_objects = []
        seen_names = set() # Add this line to keep track of seen names
        for obj in objects_data:
            obj_name = obj.get("name", "未知名稱")
            obj_type = obj.get("type")

            # Do not display special objects (type 22)
            if obj_type == 22:
                continue
            
            # Add this check for duplicate names
            if obj_name in seen_names:
                continue
            seen_names.add(obj_name)
            type_desc = ""
            if obj_type == 2:
                type_desc = "玩家"
            elif obj_type == 6:
                type_desc = "怪物/NPC"
            elif obj_type == 22:
                type_desc = "特殊物件"
            elif obj_type == 3:
                type_desc = "掉落物"
            else:
                type_desc = f"未知類型({obj_type})"
            
            display_text = f"{obj_name} ({type_desc})"
            object_listbox.insert(tk.END, display_text)
            display_objects.append({"name": obj_name, "type": obj_type})

        def add_selected_targets():
            selected_indices = object_listbox.curselection()
            if not selected_indices:
                messagebox.showwarning("未選擇", "請選擇至少一個物件。", parent=dialog)
                return
            
            current_targets = targets_text_widget.get("1.0", tk.END).strip()
            existing_targets = {t.strip() for t in current_targets.split('\n') if t.strip()}
            
            new_targets_to_add = []
            for i in selected_indices:
                obj_info = display_objects[i]
                if obj_info["name"] not in existing_targets:
                    new_targets_to_add.append(obj_info["name"])
                    existing_targets.add(obj_info["name"]) # Add to set to prevent duplicates in this session

            if new_targets_to_add:
                if current_targets:
                    targets_text_widget.insert(tk.END, "\n" + "\n".join(new_targets_to_add))
                else:
                    targets_text_widget.insert(tk.END, "\n".join(new_targets_to_add))
                self.log_message(f"[{name}] 已新增選取物件到目標列表。")
            else:
                self.log_message(f"[{name}] 沒有新的物件被新增 (可能已存在)。")
            
            dialog.destroy()

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        add_button = ttk.Button(button_frame, text="新增選取目標", command=add_selected_targets, style='Taller.TButton')
        add_button.pack(side=tk.RIGHT, padx=5)
        cancel_button = ttk.Button(button_frame, text="取消", command=dialog.destroy, style='Taller.TButton')
        cancel_button.pack(side=tk.RIGHT)

        # 所有UI元件創建完成後,設定視窗位置並顯示
        dialog.update_idletasks()
        dialog_width = 400
        dialog_height = 500
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)

    def _get_surrounding_objects(self, name):
        instance = self.instances[name]
        api = instance["script_api"]
        try:
            self.log_message(f"--- [{name}] 正在獲取周圍物件 (指令 203) ---")
            world_info_str = api.get_info(203)
            if not world_info_str:
                self.log_message(f"[{name}] 錯誤: 獲取周圍物件失敗 (RPC get_info(203) 未返回任何資料)")
                return None
            
            world_data = json.loads(world_info_str)
            if world_data.get("status") == "success":
                return world_data.get("data", [])
            else:
                self.log_message(f"[{name}] 錯誤: 指令 203 返回失敗狀態: {world_data.get('message', '未知錯誤')}")
                return None
        except Exception as e:
            self.log_message(f"[{name}] 錯誤: 獲取周圍物件時發生錯誤: {e}")
            self.handle_script_error(e, name)
            return None

    def on_specify_target_group_selected(self, name):
        instance = self.instances[name]
        ui = instance["ui"]
        
        selected_name = ui["specify_target_selected_group_name_var"].get()
        selected_index = -1
        for i, group in enumerate(ui["specify_target_groups"]):
            if group["name"] == selected_name:
                selected_index = i
                break

        if selected_index != -1:
            ui["specify_target_selected_group_index"].set(selected_index)
            # Update the hidden text area with the targets of the newly selected group
            ui["specify_target_current_targets_text"].config(state='normal')
            ui["specify_target_current_targets_text"].delete("1.0", tk.END)
            ui["specify_target_current_targets_text"].insert("1.0", ui["specify_target_groups"][selected_index]["targets"])
            ui["specify_target_current_targets_text"].config(state='disabled')
            self.log_message(f"[{name}] 已切換至目標組: {selected_name}")
        else:
            self.log_message(f"[{name}] 錯誤: 無法找到選定的目標組: {selected_name}")

    def toggle_monster_detection(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        if instance["is_monster_detecting"]:
            instance["is_monster_detecting"] = False
            self.log_message(f"[{name}] --- 正在停止怪物偵測... ---")
            ui["monster_detection_button"].config(state='disabled', text="停止中...")
            return

        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        instance["is_monster_detecting"] = True
        ui["monster_detection_button"].config(text="停止怪物偵測")
        instance["monster_detect_thread"] = threading.Thread(target=self.monster_detection_loop, args=(name,), daemon=True)
        instance["monster_detect_thread"].start()

    def _get_monster_distribution(self, name):
        instance = self.instances[name]
        api = instance.get("script_api")
        if not api:
            return None

        try:
            # 1. Get player position
            player_info_str = api.get_info(201)
            if not player_info_str:
                self.log_message(f"[{name}] [分佈偵測] 無法獲取玩家資訊。")
                return None
            
            player_json = json.loads(player_info_str)
            player_data = player_json.get('data', player_json)
            px, py = player_data.get('x'), player_data.get('y')

            if px is None or py is None:
                self.log_message(f"[{name}] [分佈偵測] 無法獲取玩家座標。")
                return None

            # 2. Get surrounding objects
            world_info_str = api.get_info(203)
            if not world_info_str:
                self.log_message(f"[{name}] [分佈偵測] 無法獲取周圍物件資訊。")
                return None
            
            world_json = json.loads(world_info_str)
            world_data = world_json.get('data', [])
            
            # 3. Filter for monsters and categorize by direction
            dir_symbols = ["↗", "→", "↘", "↓", "↙", "←", "↖", "↑"]
            monster_counts = {s: 0 for s in dir_symbols}
            
            for obj in world_data:
                if obj.get("type") == 6: # Type 6 is monster
                    mx, my = obj.get('x'), obj.get('y')
                    if mx is None or my is None: continue
                    
                    dx = mx - px
                    dy = my - py
                    
                    # 計算角度 (0~360度)
                    angle = math.degrees(math.atan2(dy, dx))
                    if angle < 0:
                        angle += 360

                    # 判斷方位（基於角度）
                    # 右上(0°), 正右(26.6°), 右下(90°), 正下(153.4°), 左下(180°), 正左(206.6°), 左上(270°), 正上(333.4°)
                    direction = None
                    if angle >= 346.7 or angle < 13.3:
                        direction = "↗" # 右上
                    elif 13.3 <= angle < 58.3:
                        direction = "→" # 正右
                    elif 58.3 <= angle < 121.7:
                        direction = "↘" # 右下
                    elif 121.7 <= angle < 166.7:
                        direction = "↓" # 正下
                    elif 166.7 <= angle < 193.3:
                        direction = "↙" # 左下
                    elif 193.3 <= angle < 238.3:
                        direction = "←" # 正左
                    elif 238.3 <= angle < 301.7:
                        direction = "↖" # 左上
                    else: # 301.7 <= angle < 346.7
                        direction = "↑" # 正上
                    
                    if direction:
                        monster_counts[direction] += 1
            
            return monster_counts

        except Exception as e:
            self.log_message(f"[{name}] [分佈偵測] 執行時發生錯誤: {e}")
            return None




    def monster_detection_loop(self, name):
        instance = self.instances[name]
        self.log_message(f"--- [{name}] 開始偵測周圍怪物分佈 ---")

        try:
            while instance["is_monster_detecting"]:
                monster_counts = self._get_monster_distribution(name)

                if monster_counts is not None:
                    distribution_str = ", ".join([f"{s}: {c}" for s, c in monster_counts.items()])
                    self.log_message(f"[{name}] [怪物分佈] {distribution_str}")

                    if sum(monster_counts.values()) > 0:
                        max_dir = max(monster_counts, key=monster_counts.get)
                        max_count = monster_counts[max_dir]
                        self.log_message(f"[{name}] [怪物偵測] 怪物最多方向: {max_dir} ({max_count}隻)")
                    else:
                        self.log_message(f"[{name}] [怪物偵測] 周圍未偵測到怪物。")
                
                # Wait
                time.sleep(1)
        except Exception as e:
            if instance["is_monster_detecting"]:
                self.log_message(f"[{name}] 怪物偵測迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] 怪物偵測結束 ---")
            if self.root.winfo_exists() and name in self.instances:
                self.root.after(0, lambda: instance["ui"]["monster_detection_button"].config(state='normal', text="開始怪物偵測"))

    def start_auto_thread(self, name, enable):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        auto_method_name = ui["auto_method_entry"].get()
        if not auto_method_name:
            return messagebox.showerror(f"[{name}] 設定錯誤", "請先在 '進階參數設定' 中填寫 'Auto Method' 的名稱。")
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        button_to_disable = ui["start_auto_button"] if enable else ui["stop_auto_button"]
        button_to_disable.config(state='disabled')

        threading.Thread(target=self.execute_auto_script, args=(name, enable), daemon=True).start()

    def execute_auto_script(self, name, enable):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            action = "啟動" if enable else "關閉"
            self.log_message(f"--- [{name}] 執行 {action} AUTO ---")
            api = instance["script_api"]
            result = api.toggle_auto(enable) 
            self.log_message(f"[{name}] RPC toggleAuto 返回: {result}")

        except Exception as e:
            self.handle_script_error(e, name)
        finally:
            if self.root.winfo_exists():
                def _reenable_buttons():
                    ui["start_auto_button"].config(state='normal')
                    ui["stop_auto_button"].config(state='normal')
                self.root.after(0, _reenable_buttons)

    def get_current_position_thread(self, name, target_x_entry=None, target_y_entry=None, button=None):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接'。")

        if button:
            button.config(state='disabled', text="讀取中")
        
        threading.Thread(target=self.execute_get_current_position, args=(name, target_x_entry, target_y_entry, button), daemon=True).start()

    def execute_get_current_position(self, name, target_x_entry=None, target_y_entry=None, button=None):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            self.log_message(f"--- [{name}] 開始讀取目前座標 ---")
            api = instance["script_api"]
            player_info_str = api.get_info(201)
            if not player_info_str: raise Exception("獲取角色資訊失敗 (RPC get_info(201) 未返回任何資料)")

            player_data = json.loads(player_info_str)
            info_dict = player_data.get('data', player_data)
            pos_x, pos_y = info_dict.get('x'), info_dict.get('y')

            if pos_x is not None and pos_y is not None:
                self.log_message(f"[{name}] 成功讀取座標: X={pos_x}, Y={pos_y}")
                def _update_ui():
                    # If target entries are provided (from coord monitor dialog), update them
                    if target_x_entry and target_y_entry:
                        target_x_entry.delete(0, tk.END)
                        target_x_entry.insert(0, str(pos_x))
                        target_y_entry.delete(0, tk.END)
                        target_y_entry.insert(0, str(pos_y))
                    else: # Otherwise, update the main x/y entries
                        ui["x_entry"].delete(0, tk.END)
                        ui["x_entry"].insert(0, str(pos_x))
                        ui["y_entry"].delete(0, tk.END)
                        ui["y_entry"].insert(0, str(pos_y))
                if self.root.winfo_exists(): self.root.after(0, _update_ui)
                return pos_x, pos_y # Return the coordinates
            else:
                self.log_message(f"[{name}] 錯誤: 在回傳的JSON中找不到座標欄位。")

        except Exception as e:
            self.log_message(f"[{name}] 錯誤: 讀取目前座標時發生錯誤: {e}")
            self.handle_script_error(e, name)
        finally:
            if button and self.root.winfo_exists():
                self.root.after(0, lambda: button.config(state='normal', text="讀取當前座標"))
        return None, None # Return None if failed

    def specify_closest_target_thread(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        target_method_name = ui["target_method_name_entry"].get()
        if not target_method_name:
            return messagebox.showerror(f"[{name}] 設定錯誤", "請先在 '進階參數設定' 中透過自動搜尋或手動填寫 '指定目標 Method' 的名稱。")

        target_names_raw = ui["specify_target_current_targets_text"].get("1.0", tk.END).strip()
        if not target_names_raw:
            return messagebox.showwarning(f"[{name}] 輸入錯誤", "請在 '目標名稱' 欄位輸入至少一個目標名稱。")
        
        target_names = [name.strip() for name in target_names_raw.split('\n') if name.strip()]

        ui["specify_target_button"].config(state='disabled', text="搜尋中...")
        threading.Thread(target=self.execute_specify_closest_target, args=(name, target_names), daemon=True).start()

    def execute_specify_closest_target(self, name, target_names, update_ui=True, log_verbose_output=True):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            if log_verbose_output: self.log_message(f"--- [{name}] 開始搜尋並指定最近目標: {target_names} ---")
            api = instance["script_api"]

            # 1. Get Player Info
            player_info_str = api.get_info(201)
            if not player_info_str: raise Exception("獲取角色資訊失敗 (RPC get_info(201) 未返回任何資料)")
            player_json = json.loads(player_info_str)
            player_data = player_json.get('data', player_json)
            px, py = player_data.get('x'), player_data.get('y')
            if px is None or py is None: raise Exception("在指令 201 的回傳中找不到玩家座標 ('x', 'y')。")

            # 2. Get Surrounding Objects
            world_info_str = api.get_info(203)
            if not world_info_str: raise Exception("獲取周圍物件失敗 (RPC get_info(203) 未返回任何資料)")
            world_json = json.loads(world_info_str)
            world_data = world_json.get('data', [])
            if not world_data:
                if log_verbose_output: self.log_message(f"[{name}] -> 周圍未發現任何物件。")
                return

            # 3. Decide which logic to use based on the checkbox
            use_priority_order = ui["specify_target_priority_var"].get()

            closest_target = None

            if use_priority_order:
                # --- Sequential Priority Logic ---
                if log_verbose_output: self.log_message(f"[{name}] -> 啟用順序優先級模式。")
                for target_line in target_names:
                    # Support multiple targets on the same priority level separated by '|'
                    sub_patterns = [p.strip() for p in target_line.split('|') if p.strip()]
                    matched_objects_at_this_level = []
                    
                    for sub_pattern in sub_patterns:
                        for obj in world_data:
                            obj_name = obj.get("name")
                            if obj.get("type") not in [2, 6, 3]: continue
                            
                            is_matched = False
                            if sub_pattern.endswith("*"):
                                if obj_name and obj_name.startswith(sub_pattern[:-1]): is_matched = True
                            elif obj_name == sub_pattern: is_matched = True
                            
                            if is_matched:
                                # Avoid duplicates if an object matches multiple patterns (unlikely but possible)
                                if obj not in matched_objects_at_this_level:
                                    matched_objects_at_this_level.append(obj)
                    
                    if matched_objects_at_this_level:
                        if log_verbose_output: self.log_message(f"[{name}] -> 在優先級 '{target_line}' 找到 {len(matched_objects_at_this_level)} 個目標，選擇最近的一個。")
                        closest_target = min(matched_objects_at_this_level, key=lambda m: math.hypot(m.get("x", px) - px, m.get("y", py) - py))
                        break # Found a target at this priority level, stop searching further down the list
            else:
                # --- Original "Closest of All" Logic ---
                if log_verbose_output: self.log_message(f"[{name}] -> 禁用順序優先級，搜尋所有目標中最近的一個。")
                all_matched_objects = []
                for obj in world_data:
                    obj_name = obj.get("name")
                    if obj.get("type") not in [2, 6, 3]: continue
                    
                    for target_name_pattern in target_names:
                        is_matched = False
                        if target_name_pattern.endswith("*"):
                            if obj_name and obj_name.startswith(target_name_pattern[:-1]): is_matched = True
                        elif obj_name == target_name_pattern: is_matched = True
                        
                        if is_matched:
                            all_matched_objects.append(obj)
                            break # Move to the next object once it's matched
                
                if all_matched_objects:
                    closest_target = min(all_matched_objects, key=lambda m: math.hypot(m.get("x", px) - px, m.get("y", py) - py))

            # 4. Set target if one was found
            if closest_target:
                target_key = closest_target.get("objectKey")
                target_name = closest_target.get("name")
                min_distance = math.hypot(closest_target.get("x", px) - px, closest_target.get("y", py) - py)
                
                self.log_message(f"[{name}] 指定最近目標: '{target_name}' (距離: {min_distance:.2f})")
                
                result = api.set_target(str(target_key))
                #if log_verbose_output: self.log_message(f"[{name}] -> RPC setTarget 返回: {result}")

                if ui["auto_attack_pickup_var"].get():
                    #if log_verbose_output: self.log_message(f"[{name}] 自動攻擊/撿取已啟用，執行 attackPickup...")
                    time.sleep(0.1)
                    attack_pickup_result = api.attack_pickup()
                    #if log_verbose_output: self.log_message(f"[{name}] RPC attackPickup 返回: {attack_pickup_result}")
            else:
                if log_verbose_output: self.log_message(f"[{name}] -> 在周圍找不到任何符合條件的目標。")

        except Exception as e:
            self.log_message(f"[{name}] 錯誤: '指定最近目標' 流程發生未知錯誤: {e}")
            self.handle_script_error(e, name)
        finally:
            if update_ui and self.root.winfo_exists():
                self.root.after(0, lambda: ui["specify_target_button"].config(state='normal', text="最近目標"))
    def execute_specify_closest_monster(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        try:
            self.log_message(f"--- [{name}] 開始搜尋並指定最近的怪物 ---")
            api = instance["script_api"]

            # 1. Get Player Info
            player_info_str = api.get_info(201)
            if not player_info_str:
                raise Exception("獲取角色資訊失敗 (RPC get_info(201) 未返回任何資料)")

            player_json = json.loads(player_info_str)
            player_data = player_json.get('data', player_json)
            px, py = player_data.get('x'), player_data.get('y')

            if px is None or py is None:
                raise Exception("在指令 201 的回傳中找不到玩家座標 ('x', 'y')。")
            self.log_message(f"[{name}] -> 玩家座標: X={px}, Y={py}")

            # 2. Get Surrounding Objects
            world_info_str = api.get_info(203)
            if not world_info_str:
                raise Exception("獲取周圍物件失敗 (RPC get_info(203) 未返回任何資料)")

            world_json = json.loads(world_info_str)
            world_data = world_json.get('data', [])
            if not world_data:
                self.log_message(f"[{name}] -> 周圍未發現任何物件。")
                return

            # 3. Find the closest monster
            closest_monster = None
            min_distance = float('inf')

            for obj in world_data:
                # Filter for monsters (type 6) that are not yourself
                if obj.get("type") == 6 and not obj.get("isMine", False):
                    mx, my = obj.get('x'), obj.get('y')
                    if mx is None or my is None:
                        continue
                    
                    distance = math.sqrt((px - mx)**2 + (py - my)**2)
                    if distance < min_distance:
                        min_distance = distance
                        closest_monster = obj
            
            if not closest_monster:
                self.log_message(f"[{name}] -> 在周圍找不到任何怪物。")
                return

            # 4. Specify the target and attack
            target_key = closest_monster.get("objectKey")
            target_name = closest_monster.get("name")
            self.log_message(f"[{name}] 最近的怪物是 '{target_name}' (距離: {min_distance:.2f})，ObjectKey: {target_key}")
            self.log_message(f"[{name}] -> 正在使用 RPC setTarget 進行指定...")
            
            result = api.set_target(str(target_key))
            self.log_message(f"[{name}] -> RPC setTarget 返回: {result}")
            
            # 5. Attack after targeting
            self.log_message(f"[{name}] -> 指定目標後，執行攻擊/撿取...")
            time.sleep(0.1) # Small delay to ensure target is set
            attack_result = api.attack_pickup()
            self.log_message(f"[{name}] -> RPC attackPickup 返回: {attack_result}")
            self.log_message(f"--- [{name}] 指定並攻擊最近怪物 '{target_name}' 完成 ---")

        except Exception as e:
            self.log_message(f"[{name}] 錯誤: '指定最近怪物' 流程發生未知錯誤: {e}")
            self.handle_script_error(e, name)

    def toggle_timed_specify_target(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        if instance["is_timed_targeting"]:
            instance["is_timed_targeting"] = False
            self.log_message(f"[{name}] --- 正在停止定時指定目標... ---")
            ui["timed_target_button"].config(state='disabled', text="停止中...")
            return

        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        try:
            interval = float(ui["timed_target_interval_entry"].get())
            if interval <= 0:
                raise ValueError("間隔必須大於 0")
        except ValueError as e:
            return messagebox.showerror(f"[{name}] 輸入錯誤", f"間隔必須是有效的正數: {e}")

        instance["is_timed_targeting"] = True
        ui["timed_target_button"].config(text="停止定時")
        instance["timed_target_thread"] = threading.Thread(target=self.timed_specify_target_loop, args=(name, interval), daemon=True)
        instance["timed_target_thread"].start()

    def toggle_all_timed_specify_target(self):
        """同時啟動或關閉所有獨立控制區塊的定時指定目標"""
        current_text = self.global_timed_target_button.cget("text")
        independent_names = [f"獨立-{i}" for i in range(1, 4)]
        
        if "啟動" in current_text:
            # 目前顯示"啟動"，執行全部啟動
            self.log_message("--- 正在啟動所有定時指定目標... ---")
            for name in independent_names:
                # 只啟動未運行的
                if name in self.instances and not self.instances[name].get("is_timed_targeting"):
                    # 檢查是否已連接
                    if self.instances[name].get("script_api"):
                        self.toggle_timed_specify_target(name)
                    else:
                        self.log_message(f"[{name}] 未連接,跳過啟動")
            
            self.global_timed_target_button.config(text="全部停止定時指定目標")
            # 啟動動畫
            if not self._global_button_animating:
                self._global_button_animating = True
                self._animate_global_button()
        else:
            # 目前顯示"停止"，執行全部停止
            self.log_message("--- 正在停止所有定時指定目標... ---")
            for name in independent_names:
                # 只停止已運行的
                if name in self.instances and self.instances[name].get("is_timed_targeting"):
                    self.toggle_timed_specify_target(name)
            
            self.global_timed_target_button.config(text="全部啟動定時指定目標")
            # 停止動畫
            self._global_button_animating = False
            self.global_timed_target_button.config(bg="#f0f0f0", fg="black") # 恢復預設顏色

    def _animate_global_button(self):
        """全域按鈕閃爍動畫"""
        if not self._global_button_animating:
            return
            
        if self._global_button_blink_state:
            self.global_timed_target_button.config(bg="#90EE90") # 亮綠色
        else:
            self.global_timed_target_button.config(bg="#32CD32") # 深綠色
            
        self._global_button_blink_state = not self._global_button_blink_state
        self.root.after(800, self._animate_global_button) # 每 0.8 秒切換一次

    def toggle_monster_hp_detection(self):
        """切換怪物血量偵測功能"""
        if self._is_hp_detecting:
            # 停止偵測
            self._is_hp_detecting = False
            self.log_message("--- 正在停止怪物血量偵測... ---")
            self.monster_hp_detection_button.config(
                text="偵測啟動",
                bg="#4CAF50",
                state='disabled'
            )
            return
        
        # 獲取怪物名稱
        monster_name = self.monster_name_entry.get().strip()
        if not monster_name:
            messagebox.showwarning("輸入錯誤", "請輸入怪物名稱")
            return
        
        # 獲取選擇的控制區塊
        selected_instance = self.detection_instance_var.get()
        connected_instance = None
        
        if selected_instance == "自動選擇":
            # 自動選擇第一個已連接的獨立控制
            independent_names = [f"獨立-{i}" for i in range(1, 4)]
            for name in independent_names:
                if name in self.instances and self.instances[name].get("script_api"):
                    connected_instance = name
                    break
        else:
            # 使用指定的控制區塊
            if selected_instance in self.instances and self.instances[selected_instance].get("script_api"):
                connected_instance = selected_instance
            else:
                messagebox.showwarning("未連接", f"{selected_instance} 尚未連接,請先連接或選擇其他區塊")
                return
        
        if not connected_instance:
            messagebox.showwarning("未連接", "請先連接至少一個獨立控制區塊")
            return
        
        # 獲取並驗證血量閾值
        try:
            hp_threshold = int(self.hp_threshold_entry.get().strip())
            if hp_threshold <= 0:
                messagebox.showwarning("輸入錯誤", "觸發血量必須大於 0")
                return
        except ValueError:
            messagebox.showwarning("輸入錯誤", "觸發血量必須是有效的數字")
            return
        
        # 啟動偵測
        self._is_hp_detecting = True
        self.monster_hp_detection_button.config(
            text="停止偵測",
            bg="#f44336"
        )
        
        # 啟動偵測執行緒,傳入血量閾值
        self._hp_detection_thread = threading.Thread(
            target=self.monster_hp_detection_loop,
            args=(monster_name, connected_instance, hp_threshold),
            daemon=True
        )
        self._hp_detection_thread.start()

    def monster_hp_detection_loop(self, monster_name, instance_name, hp_threshold):
        """怪物血量偵測迴圈"""
        instance = self.instances[instance_name]
        api = instance["script_api"]
        
        self.log_message(f"--- 開始偵測怪物 '{monster_name}' 的血量 ---")
        self.log_message(f"[使用實例: {instance_name}]")
        self.log_message(f"[觸發血量: {hp_threshold:,}]")
        
        # 使用傳入的血量閾值
        HP_THRESHOLD = hp_threshold
        CHECK_INTERVAL = 1.0  # 1秒檢查一次
        
        def update_hp_display(current_hp, max_hp, color="#666666"):
            """更新血量顯示"""
            if self.root.winfo_exists():
                hp_text = f"{current_hp:,} / {max_hp:,}"
                self.monster_hp_label.config(text=hp_text, foreground=color)
        
        try:
            while self._is_hp_detecting:
                try:
                    # 使用 203 指令獲取周圍物件
                    world_info_str = api.get_info(203)
                    
                    if not world_info_str:
                        self.log_message(f"[偵測] 無法獲取周圍物件資料")
                        self.root.after(0, lambda: update_hp_display(0, 0, "#999999"))
                        time.sleep(CHECK_INTERVAL)
                        continue
                    
                    # 解析 JSON 資料
                    world_json = json.loads(world_info_str)
                    all_objects = world_json.get('data', [])
                    
                    # 尋找所有同名的目標怪物
                    matching_monsters = []
                    for obj in all_objects:
                        # type == 6 代表怪物/NPC
                        if obj.get("type") == 6 and obj.get("name") == monster_name:
                            matching_monsters.append(obj)
                    
                    if not matching_monsters:
                        # 未發現目標怪物
                        self.root.after(0, lambda: update_hp_display(0, 0, "#999999"))
                        time.sleep(CHECK_INTERVAL)
                        continue
                    
                    # 從所有同名怪物中選擇血量最低的 (curHP最小且>0)
                    target_monster = None
                    min_hp = float('inf')
                    
                    for monster in matching_monsters:
                        cur_hp = monster.get("curHP", 0)
                        # 只考慮活著的怪物 (curHP > 0)
                        if cur_hp > 0 and cur_hp < min_hp:
                            min_hp = cur_hp
                            target_monster = monster
                    
                    # 如果沒有活著的怪物,就選第一隻
                    if not target_monster and matching_monsters:
                        target_monster = matching_monsters[0]
                    
                    if not target_monster:
                        self.root.after(0, lambda: update_hp_display(0, 0, "#999999"))
                        time.sleep(CHECK_INTERVAL)
                        continue
                    
                    # 獲取血量資訊 (使用正確的欄位名稱: curHP 和 maxHP)
                    current_hp = target_monster.get("curHP", 0)
                    max_hp = target_monster.get("maxHP", 0)
                    
                    # 記錄找到的怪物數量
                    if len(matching_monsters) > 1:
                        self.log_message(
                            f"[偵測] 發現 {len(matching_monsters)} 隻 '{monster_name}', "
                            f"選擇血量最低的: {current_hp:,}/{max_hp:,}"
                        )
                    
                    # 判斷血量顏色
                    if current_hp == 0:
                        hp_color = "#999999"  # 灰色 - 已死亡
                    elif current_hp < HP_THRESHOLD:
                        hp_color = "#f44336"  # 紅色 - 低血量
                    elif max_hp > 0 and current_hp < max_hp * 0.5:
                        hp_color = "#FF9800"  # 橙色 - 中等血量
                    else:
                        hp_color = "#4CAF50"  # 綠色 - 高血量
                    
                    # 更新 UI 顯示
                    self.root.after(0, lambda hp=current_hp, mhp=max_hp, c=hp_color: update_hp_display(hp, mhp, c))
                    
                    # 記錄血量資訊
                    if max_hp > 0:
                        percentage = (current_hp / max_hp * 100)
                        self.log_message(
                            f"[偵測] 怪物 '{monster_name}' 血量: {current_hp:,}/{max_hp:,} ({percentage:.1f}%)"
                        )
                    else:
                        self.log_message(
                            f"[偵測] 怪物 '{monster_name}' 血量: {current_hp:,}/{max_hp:,}"
                        )
                    
                    # 檢查是否觸發條件
                    if 0 < current_hp < HP_THRESHOLD:
                        self.log_message(
                            f"[偵測] ⚠️ 怪物血量低於 {HP_THRESHOLD:,}! 觸發全部啟動!"
                        )
                        
                        # 觸發全部啟動定時指定目標
                        def trigger_all():
                            # 檢查按鈕文字,如果是"啟動"才執行
                            if "啟動" in self.global_timed_target_button.cget("text"):
                                self.toggle_all_timed_specify_target()
                                self.log_message("[偵測] 已自動啟動全部定時指定目標")
                            else:
                                self.log_message("[偵測] 全部定時指定目標已在運行中,跳過觸發")
                        
                        self.root.after(0, trigger_all)
                        
                        # 停止偵測
                        self._is_hp_detecting = False
                        self.log_message("[偵測] 已觸發,停止偵測")
                        break
                    
                except json.JSONDecodeError as e:
                    self.log_message(f"[偵測] JSON 解析錯誤: {e}")
                except Exception as e:
                    self.log_message(f"[偵測] 檢查過程發生錯誤: {e}")
                
                # 等待下一次檢查
                time.sleep(CHECK_INTERVAL)
                
        except Exception as e:
            if self._is_hp_detecting:
                self.log_message(f"怪物血量偵測發生嚴重錯誤: {e}")
        finally:
            self.log_message(f"--- 怪物血量偵測結束 ---")
            if self.root.winfo_exists():
                def _reset_ui():
                    self._is_hp_detecting = False
                    self.monster_hp_detection_button.config(
                        state='normal',
                        text="偵測啟動",
                        bg="#4CAF50"
                    )
                    # 重置血量顯示
                    self.monster_hp_label.config(text="-- / --", foreground="#666666")
                self.root.after(0, _reset_ui)



    def timed_specify_target_loop(self, name, interval):
        instance = self.instances[name]
        ui = instance["ui"]
        self.log_message(f"--- [{name}] 開始定時指定目標 (間隔 {interval}s) ---")

        try:
            while instance["is_timed_targeting"]:
                target_names_raw = ui["specify_target_current_targets_text"].get("1.0", tk.END).strip()
                if not target_names_raw:
                    self.log_message(f"[{name}] 定時指定目標: 目標列表為空，自動停止。")
                    break

                target_names = [name.strip() for name in target_names_raw.split('\n') if name.strip()]
                
                # self.log_message(f"[{name}] 定時指定目標: 執行一次搜尋...")
                self.execute_specify_closest_target(name, target_names, update_ui=False, log_verbose_output=False)
                
                # Sleep for the interval, but check for the stop flag periodically
                sleep_end_time = time.time() + interval
                while time.time() < sleep_end_time:
                    if not instance["is_timed_targeting"]:
                        break
                    time.sleep(0.1)

        except Exception as e:
            if instance["is_timed_targeting"]:
                self.log_message(f"[{name}] 定時指定目標迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] 定時指定目標結束 ---")
            if self.root.winfo_exists() and name in self.instances:
                def _reset_ui():
                    instance["is_timed_targeting"] = False
                    ui["timed_target_button"].config(state='normal', text="定時指定目標")
                self.root.after(0, _reset_ui)



    def _set_auto_state(self, name, enable):
        instance = self.instances[name]
        action = "開啟" if enable else "關閉"
        self.log_message(f"[{name}] 監控座標：自動 {action} AUTO...")
        auto_method_name = instance["ui"]["auto_method_entry"].get()
        if not auto_method_name:
            self.log_message(f"[{name}] 警告: 無法自動切換AUTO，因為未在進階參數中設定 'Auto Method'。")
            return
        api = instance.get("script_api")
        if not api:
            self.log_message(f"[{name}] 警告: 無法自動切換AUTO，因為未連接。")
            return
        try:
            api.toggle_auto(enable)
            self.log_message(f"[{name}] 監控座標：成功 {action} AUTO。")
        except Exception as e:
            self.log_message(f"[{name}] 錯誤: 自動切換 AUTO 時發生錯誤: {e}")

    def _continuous_moveto_check(self, name, target_x, target_y):
        instance = self.instances[name]
        api = instance["script_api"]
        arrival_threshold = 3 
        self.log_message(f"[{name}] 超出範圍，開始自動返回程序...")
        self._set_auto_state(name, False)
        time.sleep(0.5)
        try:
            while instance["is_monitoring"]:
                try:
                    player_info_str = api.get_info(201)
                    if not player_info_str:
                        self.log_message(f"[{name}] 連續移動檢查: 無法獲取玩家資訊，中止返回程序。")
                        break
                    player_data = json.loads(player_info_str)
                    info_dict = player_data.get('data', player_data)
                    current_x, current_y = None, None
                    if 'x' in info_dict and 'y' in info_dict: current_x, current_y = info_dict['x'], info_dict['y']
                    elif 'worldX' in info_dict and 'worldY' in info_dict: current_x, current_y = info_dict['worldX'], info_dict['worldY']
                    if current_x is None or current_y is None:
                        self.log_message(f"[{name}] 連續移動檢查: 無法獲取當前座標，中止返回程序。")
                        break
                    distance = math.sqrt((current_x - target_x)**2 + (current_y - target_y)**2)
                    if distance <= arrival_threshold:
                        self.log_message(f"[{name}] 已成功返回目標點附近 (距離: {distance:.0f})。")
                        break 
                    else:
                        self.log_message(f"[{name}] 距離目標點 {distance:.0f}，執行移動指令...")
                        self.execute_moveto_script(name, target_x, target_y)
                except json.JSONDecodeError: self.log_message(f"[{name}] 連續移動檢查錯誤: 解析角色資訊JSON失敗。")
                except Exception as e: self.log_message(f"[{name}] 連續移動檢查時發生未預期錯誤: {e}")
                time.sleep(2)
        finally:
            if instance["is_monitoring"]:
                self.log_message(f"[{name}] 返回程序結束，重新開啟 AUTO...")
                self._set_auto_state(name, True)
            else:
                self.log_message(f"[{name}] 監控已手動停止，取消自動開啟 AUTO。")

    def send_telegram_notification_thread(self, name, message):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        token = "7350994544:AAEkSQnKIED_RkqzJKt0CFO9R3d9hXCzIKo"
        chat_id = ui["telegram_chat_id_entry"].get()
        if not token or not chat_id: return
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = urllib.parse.urlencode({'chat_id': chat_id, 'text': message}).encode('utf-8')
            req = urllib.request.Request(url, data=data, method='POST')
            with urllib.request.urlopen(req, timeout=10) as response:
                response_body = response.read().decode('utf-8')
                response_json = json.loads(response_body)
                if response.status == 200 and response_json.get("ok"):
                    self.log_message(f"[{name}] 成功發送 Telegram 通知。")
                else:
                    self.log_message(f"[{name}] 發送 Telegram 通知失敗: {response_body}")
        except Exception as e:
            self.log_message(f"[{name}] 發送 Telegram 通知時發生錯誤: {e}")

    def toggle_auto_barrier(self, name):
        instance = self.instances[name]
        ui = instance["ui"]
        api = instance.get("script_api")

        if instance["is_barrier_running"]:
            instance["is_barrier_running"] = False
            self.log_message(f"[{name}] --- 正在停止自動魔法屏障... ---")
            ui["barrier_toggle_button"].config(state='disabled', text="停止中...")
            return

        if not api:
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        try:
            interval = float(ui["barrier_interval_entry"].get())
        except ValueError:
            return messagebox.showerror(f"[{name}] 輸入錯誤", "間隔必須是有效的數字。")

        # --- One-time inventory check ---
        self.log_message(f"[{name}] 正在從背包中尋找 '魔法卷軸(魔法屏障)(刻印)'...")
        scroll_key = None
        try:
            inv_result = api.get_info(202)
            if inv_result:
                for item in json.loads(inv_result).get('data', []):
                    if item.get("itemName") == "魔法卷軸(魔法屏障)(刻印)":
                        scroll_key = item.get("itemKey")
                        break
            
            if scroll_key:
                self.log_message(f"[{name}] 找到卷軸，Key: {scroll_key}。將開始自動施放。")
                instance["magic_barrier_scroll_key"] = scroll_key
            else:
                messagebox.showerror(f"[{name}] 找不到卷軸", "在背包中找不到 '魔法卷軸(魔法屏障)(刻印)'!")
                return

        except Exception as e:
            self.log_message(f"[{name}] 尋找卷軸時發生錯誤: {e}")
            messagebox.showerror(f"[{name}] 錯誤", f"尋找卷軸時發生錯誤: {e}")
            return
        # --- End of check ---

        instance["is_barrier_running"] = True
        ui["barrier_toggle_button"].config(text="停止施放")
        instance["barrier_thread"] = threading.Thread(target=self.auto_barrier_loop, args=(name, interval, scroll_key), daemon=True)
        instance["barrier_thread"].start()

    def auto_barrier_loop(self, name, interval, scroll_key):
        instance = self.instances[name]
        api = instance["script_api"]
        self.log_message(f"--- [{name}] 開始自動魔法屏障 (間隔 {interval}s) ---")
        last_check = 0

        try:
            while instance["is_barrier_running"]:
                now = time.time()
                if now - last_check > interval:
                    last_check = now
                    try:
                        # Check for barrier buff
                        buff_result = api.get_info(206)
                        has_barrier = False
                        if buff_result:
                            for buff in json.loads(buff_result).get('data', []):
                                if "魔法屏障" in buff.get("buffName", ""):
                                    has_barrier = True
                                    break
                        
                        # If no barrier, use the pre-fetched scroll key
                        if not has_barrier:
                            self.log_message(f"[{name}] 未偵測到魔法屏障，使用已儲存的卷軸 Key: {scroll_key} 進行施放...")
                            api.use_item(str(scroll_key))

                    except json.JSONDecodeError as je:
                        self.log_message(f"[{name}] 自動屏障錯誤: 解析JSON失敗. {je}")
                    except Exception as e:
                        self.log_message(f"[{name}] 自動屏障迴圈內部發生錯誤: {e}")

                time.sleep(0.2) # Main loop sleep
        except Exception as e:
            if instance["is_barrier_running"]:
                self.log_message(f"[{name}] 自動屏障迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] 自動魔法屏障結束 ---")
            if self.root.winfo_exists() and name in self.instances:
                self.root.after(0, lambda: instance["ui"]["barrier_toggle_button"].config(state='normal', text="開始施放"))

    def toggle_monitoring(self, name):
        instance = self.instances[name]
        if instance["is_monitoring"]:
            instance["is_monitoring"] = False
            self.log_message(f"[{name}] --- 正在停止監控... ---")
            instance["ui"]["monitor_button"].config(state='disabled', text="停止中...")
            return
        if instance["is_seq_moving"]:
            return messagebox.showwarning(f"[{name}] 操作中", "請先停止循序移動。")
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        ui = instance["ui"]
        params = {
            "is_target_on": ui["monitor_target_var"].get(), "is_pos_on": ui["monitor_pos_var"].get(),
            "is_telegram_on": ui["telegram_notify_var"].get(),
        }
        if not any(params.values()):
            return messagebox.showwarning(f"[{name}] 未選擇", "請至少勾選一項監控功能。")
        try:
            if params["is_target_on"]:
                raw_targets = ui["target_entry"].get("1.0", tk.END).strip()
                params["targets"] = [t.strip() for t in raw_targets.replace("\n", ",").split(',') if t.strip()]
                params["target_interval"] = float(ui["target_interval_entry"].get())
                params["is_teleport_on"] = ui["monitor_target_teleport_var"].get()
                if not params["targets"]:
                    return messagebox.showwarning(f"[{name}] 輸入錯誤", "已勾選監控目標，但目標名稱為空。")
            if params["is_pos_on"]:
                params["x"] = int(ui["monitor_x_entry"].get()); params["y"] = int(ui["monitor_y_entry"].get())
                params["range"] = int(ui["monitor_range_entry"].get()); params["pos_interval"] = float(ui["pos_interval_entry"].get())
        except ValueError:
            return messagebox.showerror(f"[{name}] 輸入錯誤", "座標、範圍和間隔必須是有效的數字。" )

        # 獲取並儲存起始地圖
        api = instance["script_api"]
        if params.get("is_pos_on"): # 只在啟用座標監控時才獲取地圖
            try:
                player_info_str = api.get_info(201)
                player_data = json.loads(player_info_str)
                info_dict = player_data.get('data', player_data)
                instance["monitor_start_map"] = info_dict.get("mapName", "未知地圖")
                self.log_message(f"[{name}] 監控啟動於地圖: {instance['monitor_start_map']}")
            except Exception as e:
                instance["monitor_start_map"] = None
                self.log_message(f"[{name}] 警告: 無法讀取起始地圖: {e}")
        else:
            instance["monitor_start_map"] = None

        instance["is_monitoring"] = True
        self.set_action_buttons_state(name, 'disabled')
        ui["monitor_button"].config(state='normal', text="停止監控")
        instance["monitor_thread"] = threading.Thread(target=self.monitoring_loop, args=(name, params), daemon=True)
        instance["monitor_thread"].start()

    def reset_monitoring_ui(self, name):
        if self.root.winfo_exists() and name in self.instances:
            self.set_action_buttons_state(name, 'normal')
            self.instances[name]["ui"]["monitor_button"].config(state='normal', text="開始監控")

    def monitoring_loop(self, name, params):
        instance = self.instances[name]
        api = instance["script_api"]
        self.log_message(f"--- [{name}] 開始監控 ---") 
        if params.get("is_target_on"): self.log_message(f"[{name}] 目標監控已啟動: {params['targets']} (間隔 {params['target_interval']}s)")
        if params.get("is_pos_on"): self.log_message(f"[{name}] 座標監控已啟動: ({params['x']}, {params['y']}) 範圍 {params['range']} (間隔 {params['pos_interval']}s)")

        last_checks = {"target": 0, "pos": 0}
        start_map_name = instance.get("monitor_start_map") # 從 instance 獲取起始地圖

        try:
            while instance["is_monitoring"]:
                now = time.time()
                if params.get("is_target_on") and now - last_checks["target"] > params["target_interval"]:
                    last_checks["target"] = now
                    try:
                        player_info_str = api.get_info(201)
                        if not player_info_str: continue
                        player_data = json.loads(player_info_str)
                        info_dict = player_data.get('data', player_data)
                        if info_dict.get('zone', -1) == 1: continue
                        result = api.get_info(203)
                        if result:
                            world_data = json.loads(result)
                            if isinstance(world_data, dict) and 'data' in world_data:
                                for item in world_data['data']:
                                    if isinstance(item, dict) and item.get("name") in params["targets"]:
                                        map_name = info_dict.get("mapName", "未知地圖")
                                        pos_x, pos_y = info_dict.get("x", "N/A"), info_dict.get("y", "N/A")
                                        if params.get("is_telegram_on"):
                                            target_name = item['name']
                                            current_time = time.time()
                                            if target_name == instance["last_notified_target"] and (current_time - instance["last_notification_time"]) < 5:
                                                pass
                                            else:
                                                instance["last_notified_target"] = target_name
                                                instance["last_notification_time"] = current_time
                                                notification_message = f"[{name}] 偵測到目標: {target_name}\n地圖: {map_name}\n座標: ({pos_x}, {pos_y})"
                                                threading.Thread(target=self.send_telegram_notification_thread, args=(name, notification_message), daemon=True).start()
                                        if params.get("is_teleport_on"):
                                            instance["detection_start_time"] = time.time()
                                            self.log_message(f"--- [{name}] 在 [{map_name}] ({pos_x}, {pos_y}) 偵測到目標『{item['name']}』，執行回村 ---")
                                            self.execute_back_to_village(name)
                                            instance["is_monitoring"] = False
                                            break
                                        else:
                                            self.log_message(f"--- [{name}] 在 [{map_name}] ({pos_x}, {pos_y}) 偵測到目標『{item['name']}』，但不執行回村 ---")
                        if not instance["is_monitoring"]: continue
                    except json.JSONDecodeError: self.log_message(f"[{name}] 監控目標錯誤: 解析JSON失敗。")
                    except Exception as e: self.log_message(f"[{name}] 監控目標時發生未預期錯誤: {e}")
                
                if params.get("is_pos_on") and now - last_checks["pos"] > params["pos_interval"]:
                    last_checks["pos"] = now
                    pos_result = api.get_info(201)
                    if pos_result:
                        try:
                            player_data = json.loads(pos_result)
                            info_dict = player_data.get('data', player_data)

                            # 檢查地圖是否變更
                            current_map_name = info_dict.get("mapName", "未知地圖")
                            if start_map_name and current_map_name != start_map_name:
                                self.log_message(f"[{name}] 偵測到地圖變更 (從 '{start_map_name}' 到 '{current_map_name}')。自動停止監控。")
                                instance["is_monitoring"] = False
                                break # 立即跳出 while 迴圈

                            current_x, current_y = None, None
                            if 'x' in info_dict and 'y' in info_dict: current_x, current_y = info_dict['x'], info_dict['y']
                            elif 'worldX' in info_dict and 'worldY' in info_dict: current_x, current_y = info_dict['worldX'], info_dict['worldY']
                            if current_x is not None and current_y is not None:
                                distance = math.sqrt((current_x - params['x'])**2 + (current_y - params['y'])**2)
                                if distance > params['range']:
                                    self.log_message(f"[{name}] 超出範圍 (距離: {distance:.0f})，啟動連續移動檢查至目標點 ({params['x']}, {params['y']}) ...")
                                    threading.Thread(target=self._continuous_moveto_check, args=(name, params['x'], params['y']), daemon=True).start()
                        except json.JSONDecodeError: self.log_message(f"[{name}] 監控座標錯誤: 解析角色資訊JSON失敗。")
                        except Exception as e: self.log_message(f"[{name}] 監控座標時發生未預期錯誤: {e}")
                time.sleep(0.2)
        except Exception as e:
            if instance["is_monitoring"]:
                self.log_message(f"[{name}] 監控迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] 監控結束 ---")
            if self.root.winfo_exists(): self.root.after(0, lambda: self.reset_monitoring_ui(name))

    def start_frida_setup_thread(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        adb_path, device_serial, forward_port = ui["adb_path_entry"].get(), ui["device_serial_entry"].get(), ui["forward_port_entry"].get()
        if not all([adb_path, device_serial, forward_port]): return messagebox.showerror(f"[{name}] 輸入錯誤", "請填寫 ADB 路徑、裝置名稱和轉發 Port。")
        if not forward_port.isdigit(): return messagebox.showerror(f"[{name}] 輸入錯誤", "轉發 Port 必須是數字。")
        ui["start_frida_button"].config(state='disabled', text="設定中...")
        threading.Thread(target=self.execute_frida_setup, args=(name, adb_path, device_serial, forward_port), daemon=True).start()

    def execute_frida_setup(self, name, adb_path, device_serial, forward_port):
        try:
            self.log_message(f"--- [{name}] 開始設定 Frida 環境 ---")
            
            # 檢查 ADB 裝置連線
            if not self.ensure_adb_device(name, adb_path, device_serial):
                self.log_message(f"[{name}] ✗ ADB 連線失敗，無法繼續")
                self.root.after(0, lambda: messagebox.showerror("ADB 連線失敗", 
                    f"無法連線到裝置: {device_serial}\n\n"
                    "請確認:\n"
                    "1. 模擬器已啟動\n"
                    "2. ADB 路徑正確\n"
                    "3. 裝置序號正確"))
                return
            
            def run_adb_command(args, check_error=True):
                command = [adb_path, "-s", device_serial] + args
                  # ⭐ 顯示完整指令
                self.log_message(f"[{name}] 執行 ADB 指令: {' '.join(command)}")
                # self.log_message(f"[{name}] 執行: {' '.join(command)}") # Reduced log
                process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW)
                # if process.stdout and process.stdout.strip(): self.log_message(f"[{name}] -> {process.stdout.strip()}") # Reduced log
                # if process.stderr and process.stderr.strip(): self.log_message(f"[{name}] ADB 輸出 (stderr) -> {process.stderr.strip()}") # Reduced log
                if check_error and process.returncode != 0: raise Exception(f"ADB 指令執行失敗: {process.stderr.strip()}")
                return process.stdout.strip()

            # --- 步驟 1: 先檢查 frida-server 是否已在執行 ---
            # Try ps -A first (Android 8+), then fallback to ps
            # Note: Wrap command in quotes for su -c to handle flags like -A correctly
            ps_output = run_adb_command(["shell", "su", "-c", "ps -A"], check_error=False)
            if not ps_output or "frida-server" not in ps_output:
                 ps_output = run_adb_command(["shell", "su", "-c", "ps"], check_error=False)
            
            existing_pid = None
            if ps_output:
                for line in ps_output.splitlines():
                    if "frida-server" in line and "grep" not in line:
                        parts = line.split()
                        # Usually PID is the 2nd column (index 1)
                        # Format: USER PID ...
                        if len(parts) > 1 and parts[1].isdigit():
                            existing_pid = parts[1]
                            break
            
            if existing_pid:
                self.log_message(f"[{name}] -> 偵測到 frida-server 已在執行 (PID: {existing_pid})")
                # 即使 Frida 已運行,也要檢查並設定端口轉發
                self.log_message(f"[{name}] -> 檢查端口轉發狀態...")
                
                # 檢查端口轉發是否已建立
                forward_exists = self.check_port_forward_status(name, forward_port, 27042)
                
                if forward_exists:
                    self.log_message(f"[{name}] ✓ 端口轉發已存在")
                else:
                    self.log_message(f"[{name}] ⚠ 端口轉發不存在,正在建立...")
                    run_adb_command(["forward", f"tcp:{forward_port}", "tcp:27042"])
                    self.log_message(f"[{name}] ✓ 端口轉發設定完成 (localhost:{forward_port} -> device:27042)")
                    
                    # 更新 UI 狀態
                    instance = self.instances.get(name)
                    if instance:
                        ui = instance.get("ui", {})
                        if "forward_status_label" in ui and ui["forward_status_label"].winfo_exists():
                            def update_ui():
                                ui["forward_status_label"].config(text="● 端口轉發", foreground="green")
                            self.root.after(0, update_ui)
                
                self.log_message(f"--- [{name}] Frida 環境設定完成 ---")
                return

            # --- 步驟 2: frida-server 不存在,執行 forward ---
            self.log_message(f"[{name}] -> frida-server 未運行,開始設定端口轉發...")
            run_adb_command(["forward", f"tcp:{forward_port}", "tcp:27042"])
            self.log_message(f"[{name}] -> 端口轉發設定完成 (localhost:{forward_port} -> device:27042)")

            # --- 步驟 3: 啟動 frida-server ---
            self.log_message(f"[{name}] -> 準備啟動 frida-server...")
            start_command = [
                adb_path, "-s", device_serial,
                "shell", "su", "-c", "/data/local/tmp/frida-server &"
            ]

            # ⭐ 顯示完整 ADB 指令
            self.log_message(f"[{name}] 執行 ADB 啟動指令: {' '.join(start_command)}")

            subprocess.Popen(
                start_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            time.sleep(3)

            # 再次檢查是否啟動成功
            ps_output_check = run_adb_command(["shell", "su", "-c", "ps -A"], check_error=False)
            if not ps_output_check or "frida-server" not in ps_output_check:
                ps_output_check = run_adb_command(["shell", "su", "-c", "ps"], check_error=False)

            found_new_pid = None
            if ps_output_check:
                for line in ps_output_check.splitlines():
                    if "frida-server" in line and "grep" not in line:
                        parts = line.split()
                        if len(parts) > 1 and parts[1].isdigit():
                            found_new_pid = parts[1]
                            break

            
            if found_new_pid:
                self.log_message(f"[{name}] 成功: frida-server 正在執行 (PID: {found_new_pid})。")
                # self.root.after(0, lambda: messagebox.showinfo(f"[{name}] 成功", "Frida 設定完成！\n現在您可以點擊 '連接' 按鈕了。")) # Removed messagebox
            else:
                self.log_message(f"[{name}] 錯誤: frida-server 啟動失敗或未找到。")
                self.log_message(f"[{name}] 請確認 'frida-server' 檔案已存在於模擬器的 '/data/local/tmp/' 目錄下且有執行權限。")
                self.root.after(0, lambda: messagebox.showerror(f"[{name}] 失敗", "frida-server 啟動失敗。\n請檢查日誌確認詳情。"))
            self.log_message(f"--- [{name}] Frida 環境設定完成 ---")
        except FileNotFoundError:
            self.log_message(f"[{name}] 嚴重錯誤: 找不到 ADB 工具 '{adb_path}'。請檢查路徑是否正確。")
            self.root.after(0, lambda: messagebox.showerror(f"[{name}] ADB 錯誤", f"找不到 ADB 工具: {adb_path}"))
        except Exception as e:
            self.log_message(f"[{name}] 錯誤: Frida 設定流程發生錯誤: {e}")
            #self.root.after(0, lambda: messagebox.showerror(f"[{name}] 設定失敗", f"發生錯誤: {e}"))
            #self.root.after(0, lambda e=e: messagebox.showerror(f"[{name}] 設定失敗", f"發生錯誤: {e}"))
        finally:
            if self.root.winfo_exists():
                self.root.after(0, lambda: self.instances[name]["ui"]["start_frida_button"].config(state='normal', text="啟動 Frida 與轉發"))

    def get_first_adb_path(self):
        for instance in self.instances.values():
            adb_path = instance.get("config", {}).get("adb_path")
            if adb_path and os.path.exists(adb_path):
                self.log_message(f"[環境自檢] 使用來自 '{instance['config']['name']}' 的 ADB 路徑: {adb_path}")
                return adb_path
        default_path = "C:\\LDPlayer\\LDPlayer9\\adb.exe"
        self.log_message(f"[環境自檢] 未在設定中找到有效的 ADB 路徑，將嘗試使用預設路徑: {default_path}")
        return default_path

    def list_running_emulators(self, adb_path):
        self.log_message("--- 檢查正在運行的模擬器 ---")
        if not adb_path or not os.path.exists(adb_path):
            self.log_message("[警告] ADB 路徑未設定或無效，無法檢查模擬器.\n")
            return
        console_dir = os.path.dirname(adb_path)
        console_path = os.path.join(console_dir, "dnconsole.exe")
        if os.path.exists(console_path):
            try:
                self.log_message(f"使用 {console_path} 查詢雷電模擬器列表...")
                result = subprocess.run([console_path, "list2"], capture_output=True, text=True, encoding='gbk', errors='ignore', cwd=console_dir, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                output = result.stdout.strip()
                if output:
                    lines = output.splitlines()
                    self.log_message("找到的模擬器:")
                    count = 0
                    for line in lines:
                        parts = line.split(',')
                        if len(parts) >= 5 and parts[4] == '1':
                            index, title = int(parts[0]), parts[1]
                            serial = f"emulator-{5554 + index * 2}"
                            self.log_message(f"  > {serial}\t{title}")
                            count += 1
                    if count == 0: self.log_message("沒有找到正在運行的雷電模擬器.\n")
                    return
                else: self.log_message("dnconsole 未回傳任何可解析的輸出.\n")
            except Exception as e: self.log_message(f"[警告] 執行 dnconsole.exe 失敗: {e}，將改用 adb devices.\n")
        
        try:
            self.log_message("使用 'adb devices' 作為備用方案查詢...")
            result = subprocess.run([adb_path, "devices"], capture_output=True, text=True, encoding='utf-8', check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.stdout.strip()
            if "List of devices attached" in output and len(output.splitlines()) > 1: self.log_message(output)
            else: self.log_message("未找到任何連接的 ADB 裝置.\n")
        except Exception as e: self.log_message(f"[錯誤] 執行 'adb devices' 時發生錯誤: {e}\n")

    def list_adb_forwards(self, adb_path):
        self.log_message("--- 檢查 ADB Forwarded Ports ---")
        if not adb_path or not os.path.exists(adb_path):
            self.log_message("[警告] ADB 路徑未設定或無效，無法檢查轉發規則.\n")
            return
        try:
            result = subprocess.run([adb_path, "forward", "--list"], capture_output=True, text=True, encoding='utf-8', check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.stdout.strip()
            if output: self.log_message(output)
            else: self.log_message("未找到任何 ADB forward 規則.\n")
        except Exception as e: self.log_message(f"[錯誤] 檢查 ADB forward 列表時發生錯誤: {e}\n")

    def open_seq_move_control_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 循序移動控制")
        dialog.transient(self.root)

        seq_move_frame = ttk.Frame(dialog, padding="10")
        seq_move_frame.pack(expand=True, fill="both")
        seq_move_frame.grid_columnconfigure(0, weight=1)

        # "管理移動路線" button moved to main panel

        ttk.Label(seq_move_frame, text="選擇路線:").grid(row=1, column=0, sticky="w")
        ui["seq_move_combo"] = ttk.Combobox(seq_move_frame, state="readonly")
        ui["seq_move_combo"].grid(row=2, column=0, sticky="ew", pady=(0,5))
        ui["seq_move_combo"].bind("<<ComboboxSelected>>", lambda event, n=name: self.on_seq_move_combo_selected(n))

        ttk.Label(seq_move_frame, text="路線座標預覽:").grid(row=3, column=0, sticky="w")
        ui["seq_move_preview_text"] = scrolledtext.ScrolledText(seq_move_frame, height=10, width=30 ,wrap=tk.WORD, state='disabled')
        ui["seq_move_preview_text"].grid(row=4, column=0, sticky="ew", pady=(0,5))
        
        # 配置高亮樣式（黃色背景，黑色文字）
        ui["seq_move_preview_text"].tag_configure("highlight", background="yellow", foreground="black")
        # Arrival threshold + Move interval (同一行)
        param_frame = ttk.Frame(seq_move_frame)
        param_frame.grid(row=5, column=0, sticky="w", pady=(5, 5))

        # 抵達範圍判斷
        ttk.Label(param_frame, text="抵達範圍判斷:").pack(side=tk.LEFT, padx=(0, 5))
        ui["seq_move_threshold_entry"] = ttk.Entry(param_frame, width=4, justify="center")
        ui["seq_move_threshold_entry"].pack(side=tk.LEFT)
        default_threshold = instance.get("seq_move_threshold", "10")
        ui["seq_move_threshold_entry"].insert(0, default_threshold)

        # 移動間隔-m PyInstaller -F -w gui.py
        ttk.Label(param_frame, text="移動間隔-秒:").pack(side=tk.LEFT, padx=(10, 5))
        ui["seq_move_interval_entry"] = ttk.Entry(param_frame, width=4, justify="center")
        ui["seq_move_interval_entry"].pack(side=tk.LEFT)
        default_interval = instance.get("seq_move_interval", "2")
        ui["seq_move_interval_entry"].insert(0, default_interval)

        seq_move_buttons_frame = ttk.Frame(seq_move_frame)
        seq_move_buttons_frame.grid(row=7, column=0, sticky="ew")
        seq_move_buttons_frame.grid_columnconfigure(0, weight=1)
        seq_move_buttons_frame.grid_columnconfigure(1, weight=1)

        ui["start_seq_move_button"] = ttk.Button(seq_move_buttons_frame, text="開始循序移動", command=lambda n=name: self.run_sequential_move_thread(n), style='Taller.TButton')
        ui["start_seq_move_button"].grid(row=0, column=0, sticky="ew", padx=(0,2))
        ui["stop_seq_move_button"] = ttk.Button(seq_move_buttons_frame, text="停止", command=lambda n=name: self.stop_sequential_move(n), style='Taller.TButton')
        ui["stop_seq_move_button"].grid(row=0, column=1, sticky="ew", padx=(2,0))

        # Load data and set initial UI state
        self.update_seq_move_combo(name)
        
        # Set button states
        is_connected = instance.get("script_api") is not None
        if not is_connected:
            ui["start_seq_move_button"].config(state='disabled')
        
        if instance.get("is_seq_moving"):
            ui["start_seq_move_button"].config(state='disabled')
            ui["stop_seq_move_button"].config(state='normal')
        else:
            ui["stop_seq_move_button"].config(state='disabled')

        def _save_and_close():
            instance["seq_move_threshold"] = ui["seq_move_threshold_entry"].get()
            instance["seq_move_interval"] = ui["seq_move_interval_entry"].get()
            self.log_message(f"[{name}] 已更新循序移動的抵達範圍判斷為: {instance['seq_move_threshold']}")
            self.log_message(f"[{name}] 已更新循序移動的移動間隔為: {instance['seq_move_interval']}")


        close_button = ttk.Button(seq_move_frame, text="儲存", command=_save_and_close, style='Taller.TButton')
        close_button.grid(row=8, column=0, sticky="ew", pady=(10,0))

        # Center the dialog on the main window
        dialog.update_idletasks()
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"+{center_x}+{center_y}")

    def open_patrol_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 自動巡邏設定")
        dialog.transient(self.root)
        dialog.grab_set()

        patrol_frame = ttk.Frame(dialog, padding="10")
        patrol_frame.pack(expand=True, fill="both")
        patrol_frame.grid_columnconfigure(1, weight=1)

        # --- 按鈕 (已移至底部) --- 
        # ui["patrol_button"] = ttk.Button(patrol_frame, text="開始巡邏", command=lambda n=name: self.toggle_patrol(n), style='Taller.TButton')
        # ui["patrol_button"].grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # --- 通用設定 ---
        ttk.Label(patrol_frame, text="檢查間隔(秒):").grid(row=1, column=0, sticky="w", pady=2)
        ui["patrol_interval_entry"] = ttk.Entry(patrol_frame, width=10)
        ui["patrol_interval_entry"].grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(patrol_frame, text="抵達判斷範圍:").grid(row=2, column=0, sticky="w", pady=2)
        ui["patrol_arrival_threshold_entry"] = ttk.Entry(patrol_frame, width=10)
        ui["patrol_arrival_threshold_entry"].grid(row=2, column=1, sticky="ew", pady=2)

        # --- 觸發條件 ---
        ttk.Label(patrol_frame, text="觸發條件:").grid(row=3, column=0, sticky="w", pady=2)
        ui["patrol_condition_combo"] = ttk.Combobox(patrol_frame, values=["被攻擊者少於", "畫面無怪物"], state="readonly", width=10)
        ui["patrol_condition_combo"].grid(row=3, column=1, sticky="ew", pady=2)

        ui["patrol_attacker_threshold_label"] = ttk.Label(patrol_frame, text="攻擊者數量 <:")
        ui["patrol_attacker_threshold_label"].grid(row=4, column=0, sticky="w", pady=2)
        ui["patrol_attacker_threshold_entry"] = ttk.Entry(patrol_frame, width=10)
        ui["patrol_attacker_threshold_entry"].grid(row=4, column=1, sticky="ew", pady=2)

        # --- 近距離怪物偵測 (New) ---
        ttk.Label(patrol_frame, text="近距離保留(格):").grid(row=5, column=0, sticky="w", pady=2)
        ui["patrol_nearby_range_entry"] = ttk.Entry(patrol_frame, width=10)
        ui["patrol_nearby_range_entry"].grid(row=5, column=1, sticky="ew", pady=2)
        
        ttk.Label(patrol_frame, text="近距離數量 >:").grid(row=6, column=0, sticky="w", pady=2)
        ui["patrol_nearby_threshold_entry"] = ttk.Entry(patrol_frame, width=10)
        ui["patrol_nearby_threshold_entry"].grid(row=6, column=1, sticky="ew", pady=2)

        # --- 移動方式 ---
        ttk.Label(patrol_frame, text="移動方式:").grid(row=7, column=0, sticky="w", pady=2)
        ui["patrol_move_type_combo"] = ttk.Combobox(patrol_frame, values=["隨機移動", "路線移動"], state="readonly", width=10)
        ui["patrol_move_type_combo"].grid(row=7, column=1, sticky="ew", pady=2)

        ui["patrol_range_label"] = ttk.Label(patrol_frame, text="隨機移動範圍:")
        ui["patrol_range_label"].grid(row=8, column=0, sticky="w", pady=2)
        ui["patrol_range_entry"] = ttk.Entry(patrol_frame, width=10)
        ui["patrol_range_entry"].grid(row=8, column=1, sticky="ew", pady=2)

        ui["patrol_route_label"] = ttk.Label(patrol_frame, text="選擇路線:")
        ui["patrol_route_label"].grid(row=9, column=0, sticky="w", pady=2)
        ui["patrol_route_combo"] = ttk.Combobox(patrol_frame, state="readonly", width=10)
        ui["patrol_route_combo"].grid(row=9, column=1, sticky="ew", pady=2)
        route_names = [p["name"] for p in ui.get("seq_move_presets", [])]
        ui["patrol_route_combo"]['values'] = route_names

        # --- 其他設定 ---
        # --- 其他設定 ---
        other_settings_frame = ttk.Frame(patrol_frame)
        other_settings_frame.grid(row=10, column=0, columnspan=2, sticky="w", pady=(5,0))

        ui["patrol_toggle_auto_var"] = tk.BooleanVar()
        ttk.Checkbutton(other_settings_frame, text="移動時暫停AUTO", variable=ui["patrol_toggle_auto_var"]).pack(side=tk.LEFT)

        ui["patrol_attack_on_arrival_var"] = tk.BooleanVar()
        ttk.Checkbutton(other_settings_frame, text="選取最近的怪", variable=ui["patrol_attack_on_arrival_var"]).pack(side=tk.LEFT, padx=(10, 0))

        ui["patrol_priority_pickup_var"] = tk.BooleanVar()
        ttk.Checkbutton(other_settings_frame, text="有掉落物不移動", variable=ui["patrol_priority_pickup_var"]).pack(side=tk.LEFT, padx=(10, 0))

        # --- 動態UI邏輯 ---
        def on_condition_change(event):
            is_threshold_mode = ui["patrol_condition_combo"].get() == "被攻擊者少於"
            ui["patrol_attacker_threshold_label"].grid_remove()
            ui["patrol_attacker_threshold_entry"].grid_remove()
            if is_threshold_mode:
                ui["patrol_attacker_threshold_label"].grid(row=4, column=0, sticky="w", pady=2)
                ui["patrol_attacker_threshold_entry"].grid(row=4, column=1, sticky="ew", pady=2)

        def on_move_type_change(event):
            is_random_mode = ui["patrol_move_type_combo"].get() == "隨機移動"
            ui["patrol_range_label"].grid_remove()
            ui["patrol_range_entry"].grid_remove()
            ui["patrol_route_label"].grid_remove()
            ui["patrol_route_combo"].grid_remove()
            if is_random_mode:
                ui["patrol_range_label"].grid(row=8, column=0, sticky="w", pady=2)
                ui["patrol_range_entry"].grid(row=8, column=1, sticky="ew", pady=2)
            else:
                ui["patrol_route_label"].grid(row=9, column=0, sticky="w", pady=2)
                ui["patrol_route_combo"].grid(row=9, column=1, sticky="ew", pady=2)

        ui["patrol_condition_combo"].bind("<<ComboboxSelected>>", on_condition_change)
        ui["patrol_move_type_combo"].bind("<<ComboboxSelected>>", on_move_type_change)

        # --- 載入設定 ---
        ui["patrol_interval_entry"].insert(0, instance["config"].get("patrol_interval", "5"))
        ui["patrol_arrival_threshold_entry"].insert(0, instance["config"].get("patrol_arrival_threshold", "5"))
        ui["patrol_condition_combo"].set(instance["config"].get("patrol_condition", "被攻擊者少於"))
        ui["patrol_attacker_threshold_entry"].insert(0, instance["config"].get("patrol_attacker_threshold", "1"))
        ui["patrol_nearby_range_entry"].insert(0, instance["config"].get("patrol_nearby_range", "3"))
        ui["patrol_nearby_threshold_entry"].insert(0, instance["config"].get("patrol_nearby_threshold", "1"))
        ui["patrol_move_type_combo"].set(instance["config"].get("patrol_move_type", "隨機移動"))
        ui["patrol_range_entry"].insert(0, instance["config"].get("patrol_range", "30"))
        if instance["config"].get("patrol_selected_route_name") in route_names:
            ui["patrol_route_combo"].set(instance["config"].get("patrol_selected_route_name"))
        ui["patrol_toggle_auto_var"].set(instance["config"].get("patrol_toggle_auto", True))
        ui["patrol_attack_on_arrival_var"].set(instance["config"].get("patrol_attack_on_arrival", False))
        ui["patrol_priority_pickup_var"].set(instance["config"].get("patrol_priority_pickup", True))
        
        on_condition_change(None) # Set initial visibility
        on_move_type_change(None)



        # --- 儲存與關閉 ---
        def _save_and_close():
            instance["config"]["patrol_interval"] = ui["patrol_interval_entry"].get()
            instance["config"]["patrol_arrival_threshold"] = ui["patrol_arrival_threshold_entry"].get()
            instance["config"]["patrol_condition"] = ui["patrol_condition_combo"].get()
            instance["config"]["patrol_attacker_threshold"] = ui["patrol_attacker_threshold_entry"].get()
            instance["config"]["patrol_nearby_range"] = ui["patrol_nearby_range_entry"].get()
            instance["config"]["patrol_nearby_threshold"] = ui["patrol_nearby_threshold_entry"].get()
            instance["config"]["patrol_move_type"] = ui["patrol_move_type_combo"].get()
            instance["config"]["patrol_range"] = ui["patrol_range_entry"].get()
            instance["config"]["patrol_selected_route_name"] = ui["patrol_route_combo"].get()
            instance["config"]["patrol_toggle_auto"] = ui["patrol_toggle_auto_var"].get()
            instance["config"]["patrol_attack_on_arrival"] = ui["patrol_attack_on_arrival_var"].get()
            instance["config"]["patrol_priority_pickup"] = ui["patrol_priority_pickup_var"].get()
            self.log_message(f"[{name}] 已儲存自動巡邏設定。")
            self.save_config()

        # --- 底部按鈕區 (開始巡邏 + 儲存) ---
        bottom_btn_frame = ttk.Frame(patrol_frame)
        bottom_btn_frame.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(10,0))
        bottom_btn_frame.grid_columnconfigure(0, weight=1)
        bottom_btn_frame.grid_columnconfigure(1, weight=1)

        ui["patrol_button"] = ttk.Button(bottom_btn_frame, text="開始巡邏", command=lambda n=name: self.toggle_patrol(n), style='Taller.TButton')
        ui["patrol_button"].grid(row=0, column=1, sticky="ew", padx=(2, 0))

        close_button = ttk.Button(bottom_btn_frame, text="儲存", command=_save_and_close, style='Taller.TButton')
        close_button.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        # --- 按鈕狀態 (移至此處以確保按鈕已建立) ---
        if instance["is_patrolling"]:
            ui["patrol_button"].config(text="停止巡邏")
            ui["patrol_control_button"].config(text="自動巡邏 (運行中)")
        else:
            ui["patrol_button"].config(text="開始巡邏")
            ui["patrol_control_button"].config(text="自動巡邏設定")

        dialog.update_idletasks()
        main_win_x, main_win_y = self.root.winfo_x(), self.root.winfo_y()
        main_win_width, main_win_height = self.root.winfo_width(), self.root.winfo_height()
        dialog_width, dialog_height = 250, 280 # Increased height
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)

    def toggle_patrol(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        if instance["is_patrolling"]:
            instance["is_patrolling"] = False
            self.log_message(f"[{name}] --- 正在停止自動巡邏... ---")
            if "patrol_button" in ui and ui["patrol_button"].winfo_exists():
                ui["patrol_button"].config(state='disabled', text="停止中...")
            if "patrol_control_button" in ui and ui["patrol_control_button"].winfo_exists():
                ui["patrol_control_button"].config(text="自動巡邏設定")
            return

        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")

        try:
            params = {
                "interval": float(ui["patrol_interval_entry"].get()),
                "arrival_threshold": int(ui["patrol_arrival_threshold_entry"].get()),
                "condition": ui["patrol_condition_combo"].get(),
                "threshold": int(ui["patrol_attacker_threshold_entry"].get()),
                "nearby_range": int(ui["patrol_nearby_range_entry"].get()),
                "nearby_threshold": int(ui["patrol_nearby_threshold_entry"].get()),
                "move_type": ui["patrol_move_type_combo"].get(),
                "range": int(ui["patrol_range_entry"].get()),
                "route_name": ui["patrol_route_combo"].get(),
                "toggle_auto": ui["patrol_toggle_auto_var"].get(),
                "attack_on_arrival": ui["patrol_attack_on_arrival_var"].get(),
                "priority_pickup": ui["patrol_priority_pickup_var"].get(),
            }
            if params["move_type"] == "路線移動" and not params["route_name"]:
                return messagebox.showerror(f"[{name}] 輸入錯誤", "已選擇路線移動，但未選擇任何路線。")

        except ValueError:
            return messagebox.showerror(f"[{name}] 輸入錯誤", "間隔、數量和範圍必須是有效的數字。")

        # 獲取並印出當前狀態以供偵錯
        api = instance["script_api"]
        try:
            player_info_str = api.get_info(201)
            player_data = json.loads(player_info_str)
            info_dict = player_data.get('data', player_data)
            start_map_name = info_dict.get("mapName", "未知地圖")
        except Exception as e:
            start_map_name = f"讀取失敗: {e}"

        self.log_message(f"--- [{name}] 準備開始巡邏 ---")
        self.log_message(f"[*] 起始地圖: {start_map_name}")
        self.log_message(f"[*] 巡邏設定: {json.dumps(params, indent=2, ensure_ascii=False)}")

        instance["is_patrolling"] = True
        instance["patrol_route_index"] = 0
        instance["patrol_route_direction"] = 1 # 1 for forward, -1 for backward
        
        if "patrol_button" in ui and ui["patrol_button"].winfo_exists():
            ui["patrol_button"].config(text="停止巡邏")
        if "patrol_control_button" in ui and ui["patrol_control_button"].winfo_exists():
            ui["patrol_control_button"].config(text="自動巡邏 (運行中)")

        instance["patrol_thread"] = threading.Thread(target=self.patrol_loop, args=(name, params), daemon=True)
        instance["patrol_thread"].start()

    def execute_move_and_wait(self, name, target_x, target_y, start_map_name, arrival_threshold=5):
        instance = self.instances[name]
        api = instance["script_api"]
        move_interval = 2      # 每隔幾秒重新發送移動指令
        wait_timeout = 20      # 最長等待時間

        self.log_message(f"[{name}] 開始移動並等待抵達: ({target_x}, {target_y})")
        self.execute_moveto_script(name, target_x, target_y) # 發送第一次移動指令

        start_time = time.time()
        last_move_time = start_time

        while time.time() - start_time < wait_timeout:
            if not instance.get("is_patrolling", False): # 如果巡邏被手動停止，則退出
                self.log_message(f"[{name}] 移動等待中斷，因為巡邏已停止。")
                return

            try:
                player_info_str = api.get_info(201)
                if not player_info_str: 
                    time.sleep(0.5)
                    continue

                player_data = json.loads(player_info_str)
                info_dict = player_data.get('data', player_data)
                
                # 在移動等待中，持續檢查地圖
                current_map_name = info_dict.get("mapName", "未知地圖")
                if start_map_name and current_map_name != start_map_name:
                    self.log_message(f"[{name}] 移動中偵測到地圖變更 (從 '{start_map_name}' 到 '{current_map_name}')。停止巡邏。")
                    instance["is_patrolling"] = False
                    return # 立即退出函式

                # 檢查是否正在撿取物品 (SelectType=3)
                current_select_type = info_dict.get("selectType", 0)
                if instance.get("patrol_priority_pickup", True) and current_select_type == 3:
                    self.log_message(f"[{name}] 移動中偵測到正在撿取物品 (SelectType=3)，中斷移動。")
                    return # 中斷移動，讓外層迴圈重新判斷

                current_x, current_y = info_dict.get('x'), info_dict.get('y')

                if current_x is not None and current_y is not None:
                    distance = math.sqrt((current_x - target_x)**2 + (current_y - target_y)**2)
                    if distance <= arrival_threshold:
                        self.log_message(f"[{name}] 已抵達目標點附近 (距離: {distance:.0f})。")
                        return # 成功抵達

                    # 如果沒抵達，檢查是否需要重新發送移動指令
                    if time.time() - last_move_time > move_interval:
                        self.log_message(f"[{name}] ...尚未抵達 (距離: {distance:.0f} | 當前地圖: {current_map_name})，重新發送移動指令...")
                        self.execute_moveto_script(name, target_x, target_y)
                        last_move_time = time.time()
                
                time.sleep(0.3) # 短暫延遲避免過於頻繁的請求

            except Exception as e:
                self.log_message(f"[{name}] 等待移動時發生錯誤: {e}")
                time.sleep(1) # 發生錯誤時等待長一點
        
        self.log_message(f"[{name}] 警告: 等待移動逾時 ({wait_timeout}秒)。")


    def patrol_loop(self, name, params):
        instance = self.instances[name]
        api = instance["script_api"]
        start_map_name = None  # 用於記錄起始地圖

        move_info = ""
        if params["move_type"] == "隨機移動":
            move_info = f"範圍:{params['range']}"
        elif params["move_type"] == "路線移動":
            move_info = f"路線:{params['route_name']}"

        self.log_message(f"--- [{name}] 開始自動巡邏 (攻擊者<{params['threshold']}, 近距離({params['nearby_range']}格)<{params['nearby_threshold']}, {move_info}, 間隔:{params['interval']}s) ---")

        try:
            while instance["is_patrolling"]:
                try:
                    # 1. 獲取當前玩家資訊 (包含地圖)
                    player_info_str = api.get_info(201)
                    if not player_info_str:
                        self.log_message(f"[{name}] 巡邏：無法獲取玩家資訊，等待下一輪。")
                        time.sleep(params["interval"])
                        continue
                    
                    player_data = json.loads(player_info_str)
                    info_dict = player_data.get('data', player_data)
                    current_map_name = info_dict.get("mapName", "未知地圖")

                    # 2. 檢查地圖是否變更
                    if start_map_name is None:
                        start_map_name = current_map_name
                        # self.log_message(f"[{name}] 自動巡邏已啟動於地圖: '{start_map_name}'。離開此地圖將會自動停止。")
                    elif current_map_name != start_map_name:
                        self.log_message(f"[{name}] 偵測到地圖變更 (從 '{start_map_name}' 到 '{current_map_name}')。自動停止巡邏。")
                        instance["is_patrolling"] = False
                        continue # 立即結束此迴圈，觸發 finally 中的清理

                    # 3. 檢查攻擊者數量與近距離怪物
                    attackers_result = api.get_info(203)
                    attacker_count = 0
                    nearby_monster_count = 0
                    # nearby_item_count = 0 # 改用 selectType 判斷，不再掃描掉落物

                    # 獲取當前選擇的目標類型 (6=怪物, 3=掉落物, 2=玩家)
                    current_select_type = info_dict.get("selectType", 0)
                    
                    if attackers_result:
                        world_data = json.loads(attackers_result)
                        if isinstance(world_data, dict) and 'data' in world_data:
                            current_x, current_y = info_dict.get('x'), info_dict.get('y')
                            
                            for item in world_data['data']:
                                if isinstance(item, dict):
                                    # 計算攻擊者
                                    if item.get("attackMe"): 
                                        attacker_count += 1
                                    
                                    # 計算近距離怪物 (type=6)
                                    if item.get("type") == 6:
                                        mx, my = item.get("x"), item.get("y")
                                        if mx is not None and my is not None and current_x is not None and current_y is not None:
                                            dist = math.sqrt((mx - current_x)**2 + (my - current_y)**2)
                                            if dist <= params["nearby_range"]:
                                                nearby_monster_count += 1
                    
                    self.log_message(f"[{name}] 攻擊者: {attacker_count}, 近距離({params['nearby_range']}格)怪物: {nearby_monster_count}, 鎖定類型: {current_select_type}")

                    # 4. 判斷是否符合移動條件
                    # 條件: 
                    # 1. 攻擊者少於門檻 
                    # 2. 近距離怪物少於門檻
                    # 3. 未鎖定掉落物 (selectType != 3) (如果啟用優先撿取)
                    
                    is_busy_picking = (params.get("priority_pickup") and current_select_type == 3)
                    
                    if attacker_count < params["threshold"] and nearby_monster_count < params["nearby_threshold"]:
                        if is_busy_picking:
                            self.log_message(f"[{name}] 正在撿取物品 (SelectType=3)，暫停移動。")
                        else:
                            self.log_message(f"[{name}] 符合移動條件 (無攻擊/無近怪/無鎖定)，準備移動。")
                            
                            current_x, current_y = info_dict.get('x'), info_dict.get('y')

                        if current_x is not None and current_y is not None:
                            new_x, new_y = None, None
                            # 5. 根據移動類型計算下一點
                            if params["move_type"] == "隨機移動":
                                self.log_message(f"[{name}] 巡邏：執行怪物導向移動...")
                                monster_counts = self._get_monster_distribution(name)

                                if monster_counts and sum(monster_counts.values()) > 0:
                                    max_dir_symbol = max(monster_counts, key=monster_counts.get)
                                    self.log_message(f"[{name}] 巡邏：偵測到怪物最多方向為 {max_dir_symbol}，計算移動座標...")
                                    
                                    angles_rad = { "↗": 0, "↖": math.pi/2, "↙": math.pi, "↘": -math.pi/2 }
                                    angle_rad = angles_rad.get(max_dir_symbol, 0)
                                    
                                    distance = params["range"] # Use the patrol range as the move distance
                                    new_x = int(current_x + distance * math.cos(angle_rad))
                                    new_y = int(current_y + distance * math.sin(angle_rad))
                                    self.log_message(f"[{name}] 巡邏：移動至 {max_dir_symbol} 方向座標 ({new_x}, {new_y})")
                                else:
                                    # Fallback to original random move if no monsters found
                                    self.log_message(f"[{name}] 巡邏：周圍無怪物，執行隨機移動。")
                                    move_range = params["range"]
                                    new_x = current_x + random.randint(-move_range, move_range)
                                    new_y = current_y + random.randint(-move_range, move_range)
                            elif params["move_type"] == "路線移動":
                                self.log_message(f"[{name}] 執行路線移動...")
                                ui = instance["ui"]
                                route_name = params.get("route_name")
                                route = next((p for p in ui.get("seq_move_presets", []) if p["name"] == route_name), None)

                                if route and route.get("coords"):
                                    coords_str = route.get("coords", "")
                                    coords_list = []
                                    for line in coords_str.splitlines():
                                        line = line.strip()
                                        if not line: continue
                                        try:
                                            x_str, y_str = line.split(',')
                                            coords_list.append((int(x_str.strip()), int(y_str.strip())))
                                        except ValueError:
                                            self.log_message(f"[{name}] 錯誤: 路線 '{route_name}' 的座標格式不正確 '{line}'，已跳過。")
                                            continue

                                    if coords_list:
                                        route_len = len(coords_list)
                                        current_idx = instance.get("patrol_route_index", 0)
                                        
                                        # 取得下一個座標
                                        next_coord = coords_list[current_idx]
                                        new_x, new_y = next_coord[0], next_coord[1]
                                        
                                        # 更新 index
                                        instance["patrol_route_index"] = (current_idx + 1) % route_len
                                        self.log_message(f"[{name}] 路線 '{route_name}'，移動到點 {current_idx + 1}/{route_len}: ({new_x}, {new_y})")
                                    else:
                                        self.log_message(f"[{name}] 錯誤: 路線 '{route_name}' 中沒有有效的座標。")
                                else:
                                    self.log_message(f"[{name}] 錯誤: 找不到或路線 '{route_name}' 為空。")

                            # 如果有有效的下一點，就移動
                            if new_x is not None and new_y is not None:
                                # 根據設定決定是否開關 AUTO
                                if params.get("toggle_auto", False):
                                    self._set_auto_state(name, False) # 關閉 AUTO
                                    time.sleep(0.4) # 等待指令生效

                                # 移動並等待抵達
                                self.execute_move_and_wait(name, new_x, new_y, start_map_name, arrival_threshold=params.get("arrival_threshold", 5))

                                # 如果勾選了「到位後選取最近的怪」，則執行
                                if instance["is_patrolling"] and params.get("attack_on_arrival", False):
                                    self.log_message(f"[{name}] 已抵達，開始搜尋最近的怪物...")
                                    self.execute_specify_closest_monster(name)
                                    time.sleep(0.2) # 短暫延遲

                                # 如果之前關了，現在就打開
                                if params.get("toggle_auto", False):
                                    self._set_auto_state(name, True) # 開啟 AUTO
                            else:
                                self.log_message(f"[{name}] 未能計算出有效的下一點，跳過此次移動。")
                        else:
                            self.log_message(f"[{name}] 無法從玩家資訊中獲取座標，跳過此次移動。")

                except json.JSONDecodeError as e:
                    self.log_message(f"[{name}] 自動巡邏錯誤: 解析JSON失敗 - {e}")
                except Exception as e:
                    self.log_message(f"[{name}] 自動巡邏時發生未預期錯誤: {e}")
                
                # 等待指定間隔
                if instance["is_patrolling"]:
                    time.sleep(params["interval"])

        except Exception as e:
            if instance["is_patrolling"]:
                self.log_message(f"[{name}] 自動巡roll迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] 自動巡邏結束 ---")
            if params.get("toggle_auto", False):
                self.log_message(f"[{name}] 巡邏結束，正在關閉 AUTO...")
                self._set_auto_state(name, False)
            if self.root.winfo_exists() and name in self.instances:
                def _reset_ui():
                    ui = self.instances[name]["ui"]
                    if "patrol_button" in ui and ui["patrol_button"].winfo_exists():
                        ui["patrol_button"].config(state='normal', text="開始巡邏")
                    if "patrol_control_button" in ui and ui["patrol_control_button"].winfo_exists():
                        ui["patrol_control_button"].config(text="自動巡邏設定")
                self.root.after(0, _reset_ui)

    # --- Sequential Move Methods ---
    def open_seq_move_dialog(self, name):
        instance = self.instances[name]
        ui = instance["ui"]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 管理循序移動路線")
        dialog.transient(self.root)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1)  # Left panel (list)
        main_frame.grid_columnconfigure(1, weight=2)  # Right panel (editor)
        main_frame.grid_rowconfigure(0, weight=1)

        # Left panel (List of routes)
        left_panel = ttk.Frame(main_frame)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_panel.grid_rowconfigure(1, weight=1) # Allow listbox_frame to expand vertically
        ttk.Label(left_panel, text="已存路線:").grid(row=0, column=0, sticky="w")
        listbox_frame = ttk.Frame(left_panel)
        listbox_frame.grid(row=1, column=0, sticky="nsew")
        listbox_frame.grid_columnconfigure(0, weight=1)
        listbox_frame.grid_rowconfigure(0, weight=1)

        route_listbox = Listbox(listbox_frame, exportselection=False)
        route_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=route_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        route_listbox.config(yscrollcommand=scrollbar.set)

        # --- Buttons for reordering ---
        reorder_frame = ttk.Frame(left_panel)
        reorder_frame.grid(row=2, column=0, pady=(5,0))

        # Create a local style for the small buttons
        small_button_style = ttk.Style()
        small_button_style.configure('Small.TButton', padding=(0, 1)) # 0 horizontal, 1 vertical padding

        up_button = ttk.Button(reorder_frame, text="上移", width=10, style='Small.TButton', # Apply new style
                               command=lambda: self.move_preset_in_list(name, "up", route_listbox, temp_presets))
        up_button.pack(side=tk.LEFT, padx=2) # Remove pady, as padding is now in style
        down_button = ttk.Button(reorder_frame, text="下移", width=10, style='Small.TButton', # Apply new style
                                 command=lambda: self.move_preset_in_list(name, "down", route_listbox, temp_presets))
        down_button.pack(side=tk.LEFT, padx=2)

        # Right panel (Editing area)
        right_panel = ttk.Frame(main_frame)
        right_panel.grid(row=0, column=1, sticky="nsew")
        # right_panel.grid_columnconfigure(0, weight=1) # Removed to prevent column from expanding
        right_panel.grid_rowconfigure(3, weight=1) # Give weight to the coords_text row

        ttk.Label(right_panel, text="路線名稱:").grid(row=0, column=0, sticky="w")
        route_name_entry = ttk.Entry(right_panel, width=50) # Set a fixed width
        route_name_entry.grid(row=1, column=0, pady=(0, 5)) # Removed sticky="ew"

        ttk.Label(right_panel, text="座標 (每行 X,Y):").grid(row=2, column=0, sticky="nw")
        coords_text = scrolledtext.ScrolledText(right_panel, wrap=tk.WORD, height=10, width=50) # Set a fixed width
        coords_text.grid(row=3, column=0, sticky="nsew") # sticky="nsew" is fine for vertical expansion
        
        read_coord_button = ttk.Button(right_panel, text="讀取當前座標並加入", style='Taller.TButton',
                                       command=lambda: self.get_coord_for_seq_move_thread(name, coords_text))
        read_coord_button.grid(row=4, column=0, sticky="ew", pady=(5,0)) # Removed sticky="ew"


        # --- Dialog Logic ---
        temp_presets = [p.copy() for p in ui["seq_move_presets"]]

        def update_listbox():
            route_listbox.delete(0, tk.END)
            for preset in temp_presets:
                route_listbox.insert(tk.END, preset["name"])

        def on_listbox_select(event):
            selection_indices = route_listbox.curselection()
            if not selection_indices: return
            selected_index = selection_indices[0]
            preset = temp_presets[selected_index]
            route_name_entry.delete(0, tk.END)
            route_name_entry.insert(0, preset["name"])
            coords_text.delete("1.0", tk.END)
            coords_text.insert("1.0", preset.get("coords", ""))

        route_listbox.bind("<<ListboxSelect>>", on_listbox_select)

        def add_new():
            route_listbox.selection_clear(0, tk.END)
            route_name_entry.delete(0, tk.END)
            coords_text.delete("1.0", tk.END)
            route_name_entry.focus()

        def save_preset():
            name = route_name_entry.get().strip()
            coords = coords_text.get("1.0", tk.END).strip()
            if not name:
                messagebox.showwarning("缺少名稱", "請為路線命名。", parent=dialog)
                return

            existing_indices = [i for i, p in enumerate(temp_presets) if p["name"] == name]
            if existing_indices:
                temp_presets[existing_indices[0]]["coords"] = coords
            else:
                temp_presets.append({"name": name, "coords": coords})
            
            update_listbox()
            try:
                idx = [p["name"] for p in temp_presets].index(name)
                route_listbox.selection_set(idx)
                route_listbox.see(idx)
            except ValueError:
                pass
            self.log_message(f"[{name}] 已暫存路線 '{name}'")

        def delete_preset():
            selection_indices = route_listbox.curselection()
            if not selection_indices:
                messagebox.showwarning("未選擇", "請先從列表中選擇要刪除的路線。", parent=dialog)
                return
            
            if not messagebox.askyesno("確認刪除", f"確定要刪除路線 '{temp_presets[selection_indices[0]]['name']}' 嗎？", parent=dialog):
                return

            del temp_presets[selection_indices[0]]
            route_name_entry.delete(0, tk.END)
            coords_text.delete("1.0", tk.END)
            update_listbox()

        def save_and_close():
            ui["seq_move_presets"] = temp_presets
            self.log_message(f"[{name}] 循序移動路線已儲存。")
            if "seq_move_combo" in ui and ui["seq_move_combo"].winfo_exists():
                self.update_seq_move_combo(name)

        # Bottom buttons
        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(side="bottom", fill="x", pady=10, padx=10)
        
        ttk.Button(bottom_frame, text="新增", command=add_new, style='Taller.TButton').pack(side="left")
        ttk.Button(bottom_frame, text="儲存", command=save_preset, style='Taller.TButton').pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="刪除", command=delete_preset, style='Taller.TButton').pack(side="left")

        ttk.Button(bottom_frame, text="全部儲存", command=save_and_close, style='Taller.TButton').pack(side="right")
        ttk.Button(bottom_frame, text="取消", command=dialog.destroy, style='Taller.TButton').pack(side="right", padx=5)

        update_listbox()

        # Center the dialog
        dialog.update_idletasks()
        dialog_width = 600
        dialog_height = 450
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        self.root.wait_window(dialog)

    def move_preset_in_list(self, name, direction, listbox, temp_presets):
        selected_indices = listbox.curselection()
        if not selected_indices:
            return

        selected_index = selected_indices[0]
        
        if direction == "up":
            if selected_index == 0:
                return
            new_index = selected_index - 1
            temp_presets.insert(new_index, temp_presets.pop(selected_index))
        elif direction == "down":
            if selected_index == len(temp_presets) - 1:
                return
            new_index = selected_index + 1
            temp_presets.insert(new_index, temp_presets.pop(selected_index))
        
        # Refresh the listbox
        listbox.delete(0, tk.END)
        for preset in temp_presets:
            listbox.insert(tk.END, preset["name"])
            
        # Reselect the moved item
        listbox.selection_set(new_index)
        listbox.activate(new_index)
        listbox.see(new_index)

    def get_coord_for_seq_move_thread(self, name, text_widget):
        if not self.instances[name].get("script_api"):
            messagebox.showwarning(f"[{name}] 未連接", "請先連接才能讀取座標。")
            return
        
        def append_coords(coords):
            if coords:
                pos_x, pos_y = coords
                text_content = text_widget.get("1.0", tk.END).strip()
                if text_content:
                    text_widget.insert(tk.END, f"\n{pos_x},{pos_y}")
                else:
                    text_widget.insert(tk.END, f"{pos_x},{pos_y}")
                text_widget.see(tk.END)

        threading.Thread(target=lambda: append_coords(self.execute_get_current_position(name)), daemon=True).start()

    def update_seq_move_combo(self, name):
        ui = self.instances[name]["ui"]
        preset_names = [p["name"] for p in ui["seq_move_presets"]]
        ui["seq_move_combo"]["values"] = preset_names
        if preset_names:
            ui["seq_move_combo"].set(preset_names[0])
            self.on_seq_move_combo_selected(name)
        else:
            ui["seq_move_combo"].set("")
            self.on_seq_move_combo_selected(name)


    def on_seq_move_combo_selected(self, name):
        ui = self.instances[name]["ui"]
        selected_name = ui["seq_move_combo"].get()
        
        coords_text = ""
        for preset in ui["seq_move_presets"]:
            if preset["name"] == selected_name:
                coords_text = preset.get("coords", "")
                break
        
        preview_widget = ui["seq_move_preview_text"]
        preview_widget.config(state='normal')
        preview_widget.delete("1.0", tk.END)
        preview_widget.insert("1.0", coords_text)
        preview_widget.config(state='disabled')

    def run_sequential_move_thread(self, name):
        instance = self.instances[name]
        if instance["is_monitoring"] or instance["is_seq_moving"]:
            return messagebox.showwarning(f"[{name}] 操作中", "目前正在執行其他任務。")
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接'。")

        # 獲取並儲存起始地圖
        api = instance["script_api"]
        try:
            player_info_str = api.get_info(201)
            player_data = json.loads(player_info_str)
            info_dict = player_data.get('data', player_data)
            instance["seq_move_start_map"] = info_dict.get("mapName", "未知地圖")
            self.log_message(f"[{name}] 循序移動啟動於地圖: {instance['seq_move_start_map']}")
        except Exception as e:
            instance["seq_move_start_map"] = None
            self.log_message(f"[{name}] 警告: 無法讀取循序移動的起始地圖: {e}")

        instance["is_seq_moving"] = True
        instance["ui"]["start_seq_move_button"].config(state='disabled')
        instance["ui"]["stop_seq_move_button"].config(state='normal')
        instance["ui"]["monitor_button"].config(state='disabled')
        instance["ui"]["moveto_button"].config(state='disabled')
        instance["ui"]["back_button"].config(state='disabled')

        instance["seq_move_thread"] = threading.Thread(target=self.execute_sequential_move, args=(name,), daemon=True)
        instance["seq_move_thread"].start()

    def stop_sequential_move(self, name):
        instance = self.instances[name]
        if instance["is_seq_moving"]:
            instance["is_seq_moving"] = False
            self.log_message(f"[{name}] --- 正在停止循序移動... ---")
            instance["ui"]["stop_seq_move_button"].config(state='disabled')
            # 清除高亮
            self.update_seq_move_highlight(name, -1)

    def update_seq_move_highlight(self, name, line_index):
        """更新座標預覽框中的高亮顯示
        
        Args:
            name: 實例名稱
            line_index: 要高亮的行索引（從0開始），-1表示清除所有高亮
        """
        ui = self.instances[name]["ui"]
        if "seq_move_preview_text" not in ui or not ui["seq_move_preview_text"].winfo_exists():
            return
        
        preview_widget = ui["seq_move_preview_text"]
        
        def _update():
            # 暫時啟用 widget 以便修改
            preview_widget.config(state='normal')
            
            # 清除所有現有的高亮
            preview_widget.tag_remove("highlight", "1.0", tk.END)
            
            # 如果 line_index >= 0，則高亮指定行
            if line_index >= 0:
                # 計算行號（從1開始）
                line_num = line_index + 1
                start_pos = f"{line_num}.0"
                end_pos = f"{line_num}.end"
                
                # 應用高亮
                preview_widget.tag_add("highlight", start_pos, end_pos)
                
                # 自動捲動到高亮的行
                preview_widget.see(start_pos)
            
            # 重新禁用 widget
            preview_widget.config(state='disabled')
        
        # 確保在主線程中執行
        if self.root.winfo_exists():
            self.root.after(0, _update)

    def execute_sequential_move(self, name):
        instance, ui = self.instances[name], self.instances[name]["ui"]
        api = instance["script_api"]
        
        selected_route_name = ui["seq_move_combo"].get()
        start_map_name = instance.get("seq_move_start_map") # 獲取起始地圖

        if not selected_route_name:
            self.log_message(f"[{name}] 錯誤: 未選擇任何循序移動路線。")
            self.root.after(0, lambda: self.stop_sequential_move(name)) # Reset UI
            return

        route_data = next((p for p in ui["seq_move_presets"] if p["name"] == selected_route_name), None)
        if not route_data:
            self.log_message(f"[{name}] 錯誤: 找不到名為 '{selected_route_name}' 的路線資料。")
            self.root.after(0, lambda: self.stop_sequential_move(name))
            return

        coords_str = route_data.get("coords", "")
        coords_list = []
        for line in coords_str.splitlines():
            line = line.strip()
            if not line: continue
            try:
                x_str, y_str = line.split(',')
                coords_list.append((int(x_str.strip()), int(y_str.strip())))
            except ValueError:
                self.log_message(f"[{name}] 錯誤: 座標格式不正確 '{line}'，已跳過。")
                continue
        
        if not coords_list:
            self.log_message(f"[{name}] 錯誤: 路線 '{selected_route_name}' 中沒有有效的座標。")
            self.root.after(0, lambda: self.stop_sequential_move(name))
            return

        self.log_message(f"--- [{name}] 開始執行路線 '{selected_route_name}' ({len(coords_list)}個點) ---")
        try:
            arrival_threshold = int(ui["seq_move_threshold_entry"].get())
            move_interval = float(ui["seq_move_interval_entry"].get())
        except (ValueError, KeyError):
            arrival_threshold = 10 # Fallback to default
            move_interval = 2.0
            self.log_message(f"[{name}] 警告: 抵達範圍或移動間隔值無效，使用預設值。")
        wait_timeout = 60 # seconds

        # === 智能起點選擇：找出最近的路線點 ===
        start_index = 0  # 預設從第一個點開始
        try:
            player_info_str = api.get_info(201)
            if player_info_str:
                player_data = json.loads(player_info_str)
                info_dict = player_data.get('data', player_data)
                
                # 獲取當前座標
                current_x, current_y = None, None
                if 'x' in info_dict and 'y' in info_dict:
                    current_x, current_y = info_dict['x'], info_dict['y']
                elif 'worldX' in info_dict and 'worldY' in info_dict:
                    current_x, current_y = info_dict['worldX'], info_dict['worldY']
                
                # 計算最近的路線點
                if current_x is not None and current_y is not None:
                    min_distance = float('inf')
                    nearest_point = None
                    
                    for i, (x, y) in enumerate(coords_list):
                        distance = math.sqrt((current_x - x)**2 + (current_y - y)**2)
                        if distance < min_distance:
                            min_distance = distance
                            start_index = i
                            nearest_point = (x, y)
                    
                    self.log_message(f"[{name}] 當前座標: ({current_x}, {current_y})")
                    self.log_message(f"[{name}] 🎯 智能起點: 第 {start_index + 1} 點 {nearest_point} (距離: {min_distance:.1f})")
                else:
                    self.log_message(f"[{name}] 無法取得當前座標，從第 1 點開始")
        except Exception as e:
            self.log_message(f"[{name}] 計算最近點時發生錯誤: {e}，從第 1 點開始")

        try:
            for i in range(start_index, len(coords_list)):
                target_x, target_y = coords_list[i]
                if not instance["is_seq_moving"]:
                    self.log_message(f"[{name}] 循序移動已手動停止。")
                    break
                
                # 更新預覽框高亮（高亮當前正在移動的點）
                self.update_seq_move_highlight(name, i)
                
                self.log_message(f"[{name}] ({i+1}/{len(coords_list)}) 前往: ({target_x}, {target_y})")
                
                # Check for suspicious classname
                moveto_classname = ui["moveto_classname_entry"].get()
                if not moveto_classname or "GameHelper" in moveto_classname:
                     self.log_message(f"[{name}] 警告: MoveTo Classname 設定可能錯誤: '{moveto_classname}'。應為簡短的混淆名稱 (如 '㹏')，不含 'GameHelper'。")

                self.execute_moveto_script(name, target_x, target_y)

                start_wait_time = time.time()
                last_pos_check_time = time.time()
                last_move_time = start_wait_time
                last_known_pos = None

                while instance["is_seq_moving"]:
                    now = time.time()
                    if now - start_wait_time > wait_timeout:
                        self.log_message(f"[{name}] 警告: 等待抵達逾時 ({wait_timeout}秒)，繼續下一個點。")
                        break

                    try:
                        player_info_str = api.get_info(201)
                        if not player_info_str: 
                            time.sleep(0.2)
                            continue
                        
                        player_data = json.loads(player_info_str)
                        info_dict = player_data.get('data', player_data)
                        
                        # # 檢查地圖是否變更
                        # current_map_name = info_dict.get("mapName", "未知地圖")
                        # if start_map_name and current_map_name != start_map_name:
                        #     self.log_message(f"[{name}] 偵測到地圖變更 (從 '{start_map_name}' 到 '{current_map_name}')。自動停止循序移動。")
                        #     instance["is_seq_moving"] = False
                        #     break # 中斷內層 while 迴圈

                        current_x, current_y = None, None
                        if 'x' in info_dict and 'y' in info_dict: current_x, current_y = info_dict['x'], info_dict['y']
                        elif 'worldX' in info_dict and 'worldY' in info_dict: current_x, current_y = info_dict['worldX'], info_dict['worldY']

                        if current_x is not None and current_y is not None:
                            # --- Stuck Detection Logic ---
                            if last_known_pos is None:
                                last_known_pos = (current_x, current_y)
                                last_pos_check_time = now
                            
                            if now - last_pos_check_time > 2.0:
                                dist_moved = math.hypot(current_x - last_known_pos[0], current_y - last_known_pos[1])
                                if dist_moved < 5: # Hasn't moved much in 2 seconds
                                    self.log_message(f"[{name}] 偵測到卡住 (2秒內移動 < 5)，嘗試解鎖...")
                                    
                                    # Generate random offset for unstuck
                                    offset_x = random.choice([-1, 1]) * random.randint(30, 50)
                                    offset_y = random.choice([-1, 1]) * random.randint(30, 50)
                                    unstuck_x = current_x + offset_x
                                    unstuck_y = current_y + offset_y
                                    
                                    self.log_message(f"[{name}] 點擊解鎖點: ({unstuck_x}, {unstuck_y})")
                                    self.execute_moveto_script(name, unstuck_x, unstuck_y)
                                    time.sleep(0.5)
                                    
                                    self.log_message(f"[{name}] 重新點擊目標: ({target_x}, {target_y})")
                                    self.execute_moveto_script(name, target_x, target_y)
                                    
                                    # Reset check time and position
                                    last_pos_check_time = now
                                    last_known_pos = (current_x, current_y)
                                else:
                                    # Moved enough, update reference
                                    last_pos_check_time = now
                                    last_known_pos = (current_x, current_y)
                            # --- End Stuck Detection ---

                            distance = math.sqrt((current_x - target_x)**2 + (current_y - target_y)**2)
                            # Debug log
                            if int(now) % 5 == 0: # Log every ~5 seconds to avoid spam
                                self.log_message(f"[{name}] [DEBUG] 目前座標: ({current_x}, {current_y}), 目標: ({target_x}, {target_y}), 距離: {distance:.1f}")

                            if distance <= arrival_threshold:
                                self.log_message(f"[{name}] 已抵達點 ({target_x}, {target_y}) (距離: {distance:.0f})")
                                time.sleep(0.1) # Wait a moment after arrival
                                break # Arrived, move to next point in outer loop
                    except (json.JSONDecodeError, TypeError) as e:
                        self.log_message(f"[{name}] 循序移動中解析座標錯誤: {e}")
                    except Exception as e:
                        self.log_message(f"[{name}] 循序移動中發生未知錯誤: {e}")
                        instance["is_seq_moving"] = False # Stop on critical error
                        break
                    
                    if now - last_move_time > move_interval:
                        self.log_message(f"[{name}] ...尚未抵達，重新發送移動指令...")
                        self.execute_moveto_script(name, target_x, target_y)
                        last_move_time = now
                    
                    time.sleep(0.2)
                
                # 如果是因為地圖變更或錯誤而中斷，也要跳出外層 for 迴圈
                if not instance["is_seq_moving"]:
                    break

        except Exception as e:
            self.log_message(f"[{name}] 循序移動執行期間發生嚴重錯誤: {e}")
            self.handle_script_error(e, name)
        finally:
            if instance["is_seq_moving"]:
                self.log_message(f"--- [{name}] 路線 '{selected_route_name}' 已完成 ---")
            instance["is_seq_moving"] = False
            # 清除高亮
            self.update_seq_move_highlight(name, -1)
            if self.root.winfo_exists():
                def _reset_ui():
                    ui["start_seq_move_button"].config(state='normal')
                    ui["stop_seq_move_button"].config(state='disabled')
                    if not instance["is_monitoring"]:
                        self.set_action_buttons_state(name, 'normal')
                self.root.after(0, _reset_ui)

    # ==================== 一般掛機功能 ====================
    
    def open_general_afk_dialog(self, name):
        """開啟一般掛機設定對話框"""
        instance = self.instances[name]
        ui = instance["ui"]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 一般掛機設定")
        dialog.transient(self.root)
        dialog.resizable(True, True)
        dialog.withdraw()  # 先隱藏對話框,避免閃爍
        
        main_frame = ttk.Frame(dialog, padding="5")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)  # Notebook 區域可擴展
        main_frame.grid_rowconfigure(1, weight=0)  # 控制按鈕區域固定高度
        
        # 建立 Notebook 分頁
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        
        # BUFF 技能分頁
        buff_frame = ttk.Frame(notebook, padding="5")
        notebook.add(buff_frame, text="BUFF 技能")
        self._create_buff_skills_tab(name, buff_frame, dialog)
        
        # 攻擊技能分頁
        attack_frame = ttk.Frame(notebook, padding="5")
        notebook.add(attack_frame, text="攻擊技能")
        self._create_attack_skills_tab(name, attack_frame, dialog)

        # 其他設定區域
        settings_frame = ttk.LabelFrame(main_frame, text="其他設定", padding="5")
        settings_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0), padx=5)

        # 離開地圖後停止
        def on_stop_map_change_toggle():
            is_enabled = stop_on_map_change_var.get()
            instance["config"]["general_afk_stop_on_map_change"] = is_enabled
            status = "開啟" if is_enabled else "關閉"
            self.log_message(f"[{name}] 即時更新: 離開地圖停止掛機已{status}")
            # 如果開啟，且正在掛機中，可能需要重置起始地圖? 
            # 根據使用者需求，如果他在地圖B開啟，他希望地圖B成為新的起始點(如果還沒設定的話)，或者如果已經跑掉了就停?
            # 目前邏輯是 loop 裡會檢查 start_map_id。如果已經在跑，start_map_id 應該已經有了。
            # 如果使用者是在地圖B開啟，而 start_map_id 是地圖A，那下一次 loop 就會觸發停止。這符合預期。

        stop_on_map_change_var = tk.BooleanVar(value=instance["config"].get("general_afk_stop_on_map_change", False))
        ttk.Checkbutton(settings_frame, text="離開地圖後停止掛機", variable=stop_on_map_change_var, command=on_stop_map_change_toggle).pack(anchor="w")
        
        # 控制按鈕區
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        
        # 開始/停止按鈕
        ui["general_afk_toggle_button"] = ttk.Button(
            control_frame, 
            text="開始掛機", 
            command=lambda: self.toggle_general_afk(name),
            style='Taller.TButton'
        )
        ui["general_afk_toggle_button"].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 更新按鈕狀態
        if instance.get("is_general_afk_running", False):
            ui["general_afk_toggle_button"].config(text="停止掛機")
        
        if not instance.get("script_api"):
            ui["general_afk_toggle_button"].config(state='disabled')
        
        def save_and_close():
            instance["config"]["general_afk_stop_on_map_change"] = stop_on_map_change_var.get()
            self._save_and_close_general_afk_dialog(name, dialog)

        # 儲存並關閉按鈕
        save_button = ttk.Button(
            control_frame,
            text="儲存",
            command=save_and_close,
            style='Taller.TButton'
        )
        save_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # 狀態標籤
        ui["general_afk_dialog_status_label"] = ttk.Label(main_frame, text="一般掛機: 未啟動", foreground="blue", anchor="center")
        ui["general_afk_dialog_status_label"].grid(row=3, column=0, sticky="ew", pady=(5, 0))
        
        # 設定視窗位置(在顯示前設定)
        dialog.update_idletasks()
        dialog_width = 370  # 增加寬度以容納新的 UI
        dialog_height = 350  # 增加高度以容納新設定
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")
        
        dialog.deiconify()  # 設定好位置後再顯示對話框
        
        self.root.wait_window(dialog)
    
    def _create_buff_skills_tab(self, name, parent_frame, dialog):
        """建立 BUFF 技能設定分頁"""
        instance = self.instances[name]
        
        # 初始化 BUFF 技能列表
        if "general_afk_buff_skills" not in instance["config"]:
            instance["config"]["general_afk_buff_skills"] = []
        
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(0, weight=1)
        
        # 技能列表容器 (可捲動)
        list_frame = ttk.LabelFrame(parent_frame, text="已設定的 BUFF 技能", padding="5")
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        # 使用 Canvas + Scrollbar 實現可捲動的技能列表
        canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        skills_container = ttk.Frame(canvas)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas_window = canvas.create_window((0, 0), window=skills_container, anchor="nw")
        
        # 更新 canvas 大小
        def on_frame_configure(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 設定 canvas 寬度以匹配 frame
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        
        skills_container.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_frame_configure)
        
        # 更新列表
        def update_buff_list():
            # 清除現有的技能項目
            for widget in skills_container.winfo_children():
                widget.destroy()
            
            # 為每個技能建立一行
            for idx, skill in enumerate(instance["config"]["general_afk_buff_skills"]):
                skill_frame = ttk.Frame(skills_container)
                skill_frame.pack(fill=tk.X, pady=2, padx=2)
                
                # 啟用勾選框
                enabled_var = tk.BooleanVar(value=skill.get("enabled", True))
                
                def toggle_skill(s=skill, v=enabled_var):
                    s["enabled"] = v.get()
                
                check = ttk.Checkbutton(
                    skill_frame, 
                    text=f"{skill['skill_name']} (ID:{skill['skill_id']})",
                    variable=enabled_var,
                    command=toggle_skill
                )
                check.pack(side=tk.LEFT, fill=tk.X, expand=True)
                
                # 編輯按鈕
                edit_btn = ttk.Button(
                    skill_frame,
                    text="編輯",
                    command=lambda i=idx: edit_skill_at_index(i),
                    style='Taller.TButton',
                    width=6
                )
                edit_btn.pack(side=tk.LEFT, padx=(5, 2))
                
                # 刪除按鈕
                delete_btn = ttk.Button(
                    skill_frame,
                    text="刪除",
                    command=lambda i=idx: delete_skill_at_index(i),
                    style='Taller.TButton',
                    width=6
                )
                delete_btn.pack(side=tk.LEFT)
            
            # 更新 canvas 捲動區域
            skills_container.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        def edit_skill_at_index(idx):
            skill = instance["config"]["general_afk_buff_skills"][idx]
            self._edit_buff_skill(name, dialog, (idx, skill), update_buff_list)
        
        def delete_skill_at_index(idx):
            if messagebox.askyesno("確認刪除", "確定要刪除此 BUFF 技能嗎?"):
                del instance["config"]["general_afk_buff_skills"][idx]
                update_buff_list()
        
        update_buff_list()
        
        # 新增按鈕
        button_frame = ttk.Frame(parent_frame)
        button_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        
        add_button = ttk.Button(
            button_frame,
            text="新增 BUFF 技能",
            command=lambda: self._edit_buff_skill(name, dialog, None, update_buff_list),
            style='Taller.TButton'
        )
        add_button.pack(fill=tk.X)
    
    def _create_attack_skills_tab(self, name, parent_frame, dialog):
        """建立攻擊技能設定分頁"""
        instance = self.instances[name]
        
        # 初始化攻擊技能列表
        if "general_afk_attack_skills" not in instance["config"]:
            instance["config"]["general_afk_attack_skills"] = []
        
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(0, weight=1)
        
        # 技能列表容器 (可捲動)
        list_frame = ttk.LabelFrame(parent_frame, text="已設定的攻擊技能", padding="5")
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        # 使用 Canvas + Scrollbar 實現可捲動的技能列表
        canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        skills_container = ttk.Frame(canvas)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas_window = canvas.create_window((0, 0), window=skills_container, anchor="nw")
        
        # 更新 canvas 大小
        def on_frame_configure(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 設定 canvas 寬度以匹配 frame
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        
        skills_container.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_frame_configure)
        
        # 更新列表
        def update_attack_list():
            # 清除現有的技能項目
            for widget in skills_container.winfo_children():
                widget.destroy()
            
            # 為每個技能建立一行
            for idx, skill in enumerate(instance["config"]["general_afk_attack_skills"]):
                skill_frame = ttk.Frame(skills_container)
                skill_frame.pack(fill=tk.X, pady=2, padx=2)
                
                # 啟用勾選框
                enabled_var = tk.BooleanVar(value=skill.get("enabled", True))
                
                def toggle_skill(s=skill, v=enabled_var):
                    s["enabled"] = v.get()
                
                # 顯示技能名稱和 MP 條件
                mp_cond = skill.get("mp_condition", ">=")
                mp_threshold = skill.get("mp_threshold", 100)
                display_text = f"{skill['skill_name']} (ID:{skill['skill_id']}, MP{mp_cond}{mp_threshold}%)"
                
                check = ttk.Checkbutton(
                    skill_frame, 
                    text=display_text,
                    variable=enabled_var,
                    command=toggle_skill
                )
                check.pack(side=tk.LEFT, fill=tk.X, expand=True)
                
                # 編輯按鈕
                edit_btn = ttk.Button(
                    skill_frame,
                    text="編輯",
                    command=lambda i=idx: edit_skill_at_index(i),
                    style='Taller.TButton',
                    width=6
                )
                edit_btn.pack(side=tk.LEFT, padx=(5, 2))
                
                # 刪除按鈕
                delete_btn = ttk.Button(
                    skill_frame,
                    text="刪除",
                    command=lambda i=idx: delete_skill_at_index(i),
                    style='Taller.TButton',
                    width=6
                )
                delete_btn.pack(side=tk.LEFT)
            
            # 更新 canvas 捲動區域
            skills_container.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        def edit_skill_at_index(idx):
            skill = instance["config"]["general_afk_attack_skills"][idx]
            self._edit_attack_skill(name, dialog, (idx, skill), update_attack_list)
        
        def delete_skill_at_index(idx):
            if messagebox.askyesno("確認刪除", "確定要刪除此攻擊技能嗎?"):
                del instance["config"]["general_afk_attack_skills"][idx]
                update_attack_list()
        
        update_attack_list()
        
        # 新增按鈕
        button_frame = ttk.Frame(parent_frame)
        button_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        
        add_button = ttk.Button(
            button_frame,
            text="新增攻擊技能",
            command=lambda: self._edit_attack_skill(name, dialog, None, update_attack_list),
            style='Taller.TButton'
        )
        add_button.pack(fill=tk.X)  
    
    def _edit_buff_skill_selected(self, name, parent_dialog, listbox, update_callback):
        """編輯選中的 BUFF 技能"""
        selection = listbox.curselection()
        if not selection:
            messagebox.showwarning("未選擇", "請先選擇要編輯的技能。", parent=parent_dialog)
            return
        
        index = selection[0]
        instance = self.instances[name]
        skill = instance["config"]["general_afk_buff_skills"][index]
        self._edit_buff_skill(name, parent_dialog, (index, skill), update_callback)
    
    def _edit_attack_skill_selected(self, name, parent_dialog, listbox, update_callback):
        """編輯選中的攻擊技能"""
        selection = listbox.curselection()
        if not selection:
            messagebox.showwarning("未選擇", "請先選擇要編輯的技能。", parent=parent_dialog)
            return
        
        index = selection[0]
        instance = self.instances[name]
        skill = instance["config"]["general_afk_attack_skills"][index]
        self._edit_attack_skill(name, parent_dialog, (index, skill), update_callback)
    
    def _edit_buff_skill(self, name, parent_dialog, skill_data, update_callback):
        """編輯或新增 BUFF 技能"""
        instance = self.instances[name]
        
        # skill_data 是 (index, skill_dict) 或 None (新增)
        is_edit = skill_data is not None
        if is_edit:
            index, skill = skill_data
        else:
            skill = {
                "skill_id": 0,
                "skill_name": "",
                "buff_id": 0,
                "check_time": True,
                "time_threshold": 30,
                "check_missing": True,
                "cooldown": 5
            }
        
        edit_dialog = tk.Toplevel(parent_dialog)
        edit_dialog.title(f"[{name}] {'編輯' if is_edit else '新增'} BUFF 技能")
        edit_dialog.transient(parent_dialog)
        edit_dialog.grab_set()
        
        main_frame = ttk.Frame(edit_dialog, padding="5")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(1, weight=1)
        
        row = 0
        
        # 技能選擇
        ttk.Label(main_frame, text="技能:").grid(row=row, column=0, sticky="w", pady=1)
        skill_frame = ttk.Frame(main_frame)
        skill_frame.grid(row=row, column=1, sticky="ew", pady=1)
        
        skill_id_var = tk.StringVar(value=str(skill["skill_id"]) if skill["skill_id"] else "")
        skill_name_var = tk.StringVar(value=skill["skill_name"])
        
        skill_id_entry = ttk.Entry(skill_frame, textvariable=skill_id_var, width=10)
        skill_id_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        skill_name_label = ttk.Label(skill_frame, textvariable=skill_name_var, foreground="blue")
        skill_name_label.pack(side=tk.LEFT, padx=(0, 5))
        
        select_skill_button = ttk.Button(
            skill_frame,
            text="選擇技能",
            command=lambda: self._select_skill_for_buff(name, skill_id_var, skill_name_var, select_skill_button),
            style='Taller.TButton'
        )
        select_skill_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 測試技能按鈕
        test_skill_button = ttk.Button(
            skill_frame,
            text="測試",
            command=lambda: self._test_skill(name, skill_id_var),
            style='Taller.TButton'
        )
        test_skill_button.pack(side=tk.LEFT)
        
        row += 1
        
        # BUFF ID
        ttk.Label(main_frame, text="BUFF ID:").grid(row=row, column=0, sticky="w", pady=1)
        
        buff_id_frame = ttk.Frame(main_frame)
        buff_id_frame.grid(row=row, column=1, sticky="ew", pady=1)
        
        buff_id_var = tk.StringVar(value=str(skill["buff_id"]) if skill["buff_id"] else "")
        buff_id_entry = ttk.Entry(buff_id_frame, textvariable=buff_id_var, width=10)
        buff_id_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        select_buff_button = ttk.Button(
            buff_id_frame,
            text="選擇 BUFF",
            command=lambda: self._select_buff_id(name, buff_id_var, select_buff_button),
            style='Taller.TButton'
        )
        select_buff_button.pack(side=tk.LEFT)
        
        row += 1
        
        # 條件設定
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)
        row += 1
        
        ttk.Label(main_frame, text="施放條件:", font=("", 9, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=1)
        row += 1
        
        # 剩餘時間條件
        check_time_var = tk.BooleanVar(value=skill["check_time"])
        time_threshold_var = tk.StringVar(value=str(skill["time_threshold"]))
        
        time_frame = ttk.Frame(main_frame)
        time_frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=1)
        
        ttk.Checkbutton(time_frame, text="剩餘時間 <=", variable=check_time_var).pack(side=tk.LEFT)
        ttk.Entry(time_frame, textvariable=time_threshold_var, width=8).pack(side=tk.LEFT, padx=(5, 5))
        ttk.Label(time_frame, text="秒").pack(side=tk.LEFT)
        
        row += 1
        
        # 未擁有條件
        check_missing_var = tk.BooleanVar(value=skill["check_missing"])
        ttk.Checkbutton(main_frame, text="未擁有該 BUFF 時施放", variable=check_missing_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=1)
        
        row += 1
        
        # 冷卻時間
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)
        row += 1
        
        ttk.Label(main_frame, text="施放冷卻(秒):").grid(row=row, column=0, sticky="w", pady=1)
        cooldown_var = tk.StringVar(value=str(skill["cooldown"]))
        ttk.Entry(main_frame, textvariable=cooldown_var, width=10).grid(row=row, column=1, sticky="w", pady=1)
        
        row += 1
        
        # 儲存按鈕
        def save_skill():
            try:
                new_skill = {
                    "skill_id": int(skill_id_var.get()) if skill_id_var.get() else 0,
                    "skill_name": skill_name_var.get(),
                    "buff_id": int(buff_id_var.get()) if buff_id_var.get() else 0,
                    "check_time": check_time_var.get(),
                    "time_threshold": int(time_threshold_var.get()),
                    "check_missing": check_missing_var.get(),
                    "cooldown": float(cooldown_var.get()),
                    "enabled": skill.get("enabled", True) if is_edit else True  # 新增時預設啟用,編輯時保留原狀態
                }
                
                if new_skill["skill_id"] == 0:
                    messagebox.showerror("錯誤", "請選擇技能!", parent=edit_dialog)
                    return
                
                if is_edit:
                    instance["config"]["general_afk_buff_skills"][index] = new_skill
                else:
                    instance["config"]["general_afk_buff_skills"].append(new_skill)
                
                update_callback()
                edit_dialog.destroy()
                
            except ValueError as e:
                messagebox.showerror("錯誤", f"輸入格式錯誤: {e}", parent=edit_dialog)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=(5, 0))
        
        ttk.Button(button_frame, text="儲存", command=save_skill, style='Taller.TButton').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="取消", command=edit_dialog.destroy, style='Taller.TButton').pack(side=tk.LEFT)
        
        # 設定視窗位置
        edit_dialog.update_idletasks()
        dialog_width = 400
        dialog_height = edit_dialog.winfo_height()
        parent_x = parent_dialog.winfo_x()
        parent_y = parent_dialog.winfo_y()
        parent_width = parent_dialog.winfo_width()
        parent_height = parent_dialog.winfo_height()
        center_x = parent_x + (parent_width - dialog_width) // 2
        center_y = parent_y + (parent_height - dialog_height) // 2
        edit_dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")
    
    def _edit_attack_skill(self, name, parent_dialog, skill_data, update_callback):
        """編輯或新增攻擊技能"""
        instance = self.instances[name]
        
        is_edit = skill_data is not None
        if is_edit:
            index, skill = skill_data
        else:
            skill = {
                "skill_id": 0,
                "skill_name": "",
                "mp_condition": ">=",  # 預設大於等於
                "mp_threshold": 100,
                "interval": 2,
                "check_cooldown": True
            }
        
        edit_dialog = tk.Toplevel(parent_dialog)
        edit_dialog.title(f"[{name}] {'編輯' if is_edit else '新增'} 攻擊技能")
        edit_dialog.transient(parent_dialog)
        edit_dialog.grab_set()
        
        main_frame = ttk.Frame(edit_dialog, padding="5")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(1, weight=1)
        
        row = 0
        
        # 技能選擇
        ttk.Label(main_frame, text="技能:").grid(row=row, column=0, sticky="w", pady=1)
        skill_frame = ttk.Frame(main_frame)
        skill_frame.grid(row=row, column=1, sticky="ew", pady=1)
        
        skill_id_var = tk.StringVar(value=str(skill["skill_id"]) if skill["skill_id"] else "")
        skill_name_var = tk.StringVar(value=skill["skill_name"])
        
        skill_id_entry = ttk.Entry(skill_frame, textvariable=skill_id_var, width=10)
        skill_id_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        skill_name_label = ttk.Label(skill_frame, textvariable=skill_name_var, foreground="blue")
        skill_name_label.pack(side=tk.LEFT, padx=(0, 5))
        
        select_skill_button = ttk.Button(
            skill_frame,
            text="選擇技能",
            command=lambda: self._select_skill_for_attack(name, skill_id_var, skill_name_var, select_skill_button),
            style='Taller.TButton'
        )
        select_skill_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 測試技能按鈕
        test_skill_button = ttk.Button(
            skill_frame,
            text="測試",
            command=lambda: self._test_skill(name, skill_id_var),
            style='Taller.TButton'
        )
        test_skill_button.pack(side=tk.LEFT)
        
        row += 1
        
        # MP 門檻
        ttk.Label(main_frame, text="MP 條件:").grid(row=row, column=0, sticky="w", pady=1)
        mp_frame = ttk.Frame(main_frame)
        mp_frame.grid(row=row, column=1, sticky="w", pady=1)
        
        ttk.Label(mp_frame, text="MP").pack(side=tk.LEFT)
        
        mp_condition_var = tk.StringVar(value=skill.get("mp_condition", ">="))
        mp_condition_combo = ttk.Combobox(mp_frame, textvariable=mp_condition_var, values=[">=", "<="], width=3, state="readonly")
        mp_condition_combo.pack(side=tk.LEFT, padx=(5, 5))
        
        mp_threshold_var = tk.StringVar(value=str(skill["mp_threshold"]))
        ttk.Entry(mp_frame, textvariable=mp_threshold_var, width=5).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(mp_frame, text="% 時使用").pack(side=tk.LEFT)
        
        row += 1
        
        # 使用間隔
        ttk.Label(main_frame, text="使用間隔(秒):").grid(row=row, column=0, sticky="w", pady=1)
        interval_var = tk.StringVar(value=str(skill["interval"]))
        ttk.Entry(main_frame, textvariable=interval_var, width=10).grid(row=row, column=1, sticky="w", pady=1)
        
        row += 1
        
        # 檢查冷卻
        check_cooldown_var = tk.BooleanVar(value=skill["check_cooldown"])
        ttk.Checkbutton(main_frame, text="檢查技能冷卻", variable=check_cooldown_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=1)
        
        row += 1
        
        # 儲存按鈕
        def save_skill():
            try:
                new_skill = {
                    "skill_id": int(skill_id_var.get()) if skill_id_var.get() else 0,
                    "skill_name": skill_name_var.get(),
                    "mp_condition": mp_condition_var.get(),
                    "mp_threshold": int(mp_threshold_var.get()),
                    "interval": float(interval_var.get()),
                    "check_cooldown": check_cooldown_var.get(),
                    "enabled": skill.get("enabled", True) if is_edit else True  # 新增時預設啟用,編輯時保留原狀態
                }
                
                if new_skill["skill_id"] == 0:
                    messagebox.showerror("錯誤", "請選擇技能!", parent=edit_dialog)
                    return
                
                if is_edit:
                    instance["config"]["general_afk_attack_skills"][index] = new_skill
                else:
                    instance["config"]["general_afk_attack_skills"].append(new_skill)
                
                update_callback()
                edit_dialog.destroy()
                
            except ValueError as e:
                messagebox.showerror("錯誤", f"輸入格式錯誤: {e}", parent=edit_dialog)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=(5, 0))
        
        ttk.Button(button_frame, text="儲存", command=save_skill, style='Taller.TButton').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="取消", command=edit_dialog.destroy, style='Taller.TButton').pack(side=tk.LEFT)
        
        # 設定視窗位置
        edit_dialog.update_idletasks()
        dialog_width = 350
        dialog_height = edit_dialog.winfo_height()
        parent_x = parent_dialog.winfo_x()
        parent_y = parent_dialog.winfo_y()
        parent_width = parent_dialog.winfo_width()
        parent_height = parent_dialog.winfo_height()
        center_x = parent_x + (parent_width - dialog_width) // 2
        center_y = parent_y + (parent_height - dialog_height) // 2
        edit_dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")
    
    def _delete_buff_skill(self, name, listbox, update_callback):
        """刪除 BUFF 技能"""
        selection = listbox.curselection()
        if not selection:
            messagebox.showwarning("未選擇", "請先選擇要刪除的技能。")
            return
        
        if messagebox.askyesno("確認刪除", "確定要刪除此 BUFF 技能嗎?"):
            index = selection[0]
            instance = self.instances[name]
            del instance["config"]["general_afk_buff_skills"][index]
            update_callback()
    
    def _delete_attack_skill(self, name, listbox, update_callback):
        """刪除攻擊技能"""
        selection = listbox.curselection()
        if not selection:
            messagebox.showwarning("未選擇", "請先選擇要刪除的技能。")
            return
        
        if messagebox.askyesno("確認刪除", "確定要刪除此攻擊技能嗎?"):
            index = selection[0]
            instance = self.instances[name]
            del instance["config"]["general_afk_attack_skills"][index]
            update_callback()
    
    def _test_skill(self, name, skill_id_var):
        """測試技能"""
        instance = self.instances[name]
        api = instance.get("script_api")
        
        if not api:
            messagebox.showwarning("未連接", "請先連接到遊戲!")
            return
        
        try:
            skill_id = int(skill_id_var.get()) if skill_id_var.get() else 0
            if skill_id == 0:
                messagebox.showwarning("未選擇技能", "請先選擇或輸入技能 ID!")
                return
            
            # 施放技能
            result = api.use_skill(skill_id, "0")
            self.log_message(f"[{name}] 測試技能 ID: {skill_id}")
            messagebox.showinfo("測試成功", f"已施放技能 ID: {skill_id}\n\n請查看遊戲中的效果。")
            
        except ValueError:
            messagebox.showerror("錯誤", "技能 ID 必須是數字!")
        except Exception as e:
            messagebox.showerror("錯誤", f"測試技能失敗: {e}")
            self.log_message(f"[{name}] 測試技能失敗: {e}")
    
    def _select_skill_for_buff(self, name, skill_id_var, skill_name_var, button):
        """為 BUFF 技能選擇技能"""
        if button:
            button.config(state='disabled')
        
        def callback(skill_id, skill_name):
            skill_id_var.set(str(skill_id))
            skill_name_var.set(skill_name)
            if button:
                button.config(state='normal')
        
        threading.Thread(
            target=self._execute_select_skill_generic_with_callback,
            args=(name, callback, button),
            daemon=True
        ).start()
    
    def _select_skill_for_attack(self, name, skill_id_var, skill_name_var, button):
        """為攻擊技能選擇技能"""
        if button:
            button.config(state='disabled')
        
        def callback(skill_id, skill_name):
            skill_id_var.set(str(skill_id))
            skill_name_var.set(skill_name)
            if button:
                button.config(state='normal')
        
        threading.Thread(
            target=self._execute_select_skill_generic_with_callback,
            args=(name, callback, button),
            daemon=True
        ).start()
    
    def _select_buff_id(self, name, buff_id_var, button):
        """選擇 BUFF ID"""
        if button:
            button.config(state='disabled')
        
        def callback(buff_id):
            buff_id_var.set(str(buff_id))
            if button:
                button.config(state='normal')
        
        threading.Thread(
            target=self._execute_select_buff_generic_with_callback,
            args=(name, callback, button),
            daemon=True
        ).start()
    
    def _execute_select_buff_generic_with_callback(self, name, callback, button):
        """執行 BUFF 選擇並回調"""
        instance = self.instances[name]
        api = instance.get("script_api")
        if not api:
            self.log_message(f"[{name}] 獲取 BUFF 失敗: 未連接。")
            if button:
                self.root.after(0, lambda: button.config(state='normal'))
            return
        
        try:
            buff_list_str = api.get_info(206)
            if not buff_list_str:
                raise Exception("獲取 BUFF 列表失敗 (RPC get_info(206) 未返回任何資料)")
            
            buff_data = json.loads(buff_list_str)
            if buff_data.get("status") != "success":
                raise Exception(f"指令 206 返回失敗狀態: {buff_data.get('message', '未知錯誤')}")
            
            buffs = buff_data.get("data", [])
            
            if self.root.winfo_exists():
                def _show_dialog():
                    selected_id = self._show_buff_selection_dialog_and_get_id(name, buffs)
                    if selected_id is not None:
                        callback(selected_id)
                    elif button:
                         button.config(state='normal')
                
                self.root.after(0, _show_dialog)
        
        except Exception as e:
            self.log_message(f"[{name}] 獲取或選擇 BUFF 時發生錯誤: {e}")
            self.handle_script_error(e, name)
            if button:
                self.root.after(0, lambda: button.config(state='normal'))

    def _show_buff_selection_dialog_and_get_id(self, name, buffs):
        """顯示 BUFF 選擇對話框並返回選中的 ID"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"[{name}] 選擇 BUFF")
        
        # 設定對話框位置
        dialog_width = 400
        dialog_height = 500
        main_win_x = self.root.winfo_x()
        main_win_y = self.root.winfo_y()
        main_win_width = self.root.winfo_width()
        main_win_height = self.root.winfo_height()
        center_x = main_win_x + (main_win_width - dialog_width) // 2
        center_y = main_win_y + (main_win_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")
        
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 搜尋框
        search_frame = ttk.Frame(dialog, padding="5")
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="搜尋:").pack(side=tk.LEFT)
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 列表框
        list_frame = ttk.Frame(dialog, padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        listbox = Listbox(list_frame, selectmode=tk.SINGLE, font=("Consolas", 10))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)
        
        # 填充列表
        def update_list(*args):
            search_term = search_var.get().lower()
            listbox.delete(0, tk.END)
            
            for buff in buffs:
                buff_id = buff.get("buffID")
                buff_name = buff.get("buffName", "未知")
                remain_time = buff.get("remainTime", 0) / 1000
                display_text = f"ID:{buff_id:<5} {buff_name} ({remain_time:.0f}s)"
                
                if search_term in str(buff_id) or search_term in buff_name.lower():
                    listbox.insert(tk.END, display_text)
        
        search_var.trace("w", update_list)
        update_list()
        
        selected_id = [None]
        
        def on_select():
            selection = listbox.curselection()
            if selection:
                index = selection[0]
                item_text = listbox.get(index)
                # 解析 ID: "ID:123   名稱..."
                try:
                    buff_id = int(item_text.split()[0].split(":")[1])
                    selected_id[0] = buff_id
                    dialog.destroy()
                except:
                    pass
        
        ttk.Button(dialog, text="選擇", command=on_select, style='Taller.TButton').pack(pady=10)
        
        # 雙擊選擇
        listbox.bind('<Double-1>', lambda e: on_select())
        
        self.root.wait_window(dialog)
        return selected_id[0]
    
    def _execute_select_skill_generic_with_callback(self, name, callback, button):
        """執行技能選擇並回調"""
        instance = self.instances[name]
        api = instance.get("script_api")
        if not api:
            self.log_message(f"[{name}] 獲取技能失敗: 未連接。")
            if button:
                self.root.after(0, lambda: button.config(state='normal'))
            return
        
        try:
            skills_str = api.get_info(218)
            if not skills_str:
                raise Exception("獲取技能列表失敗 (RPC get_info(218) 未返回任何資料)")
            
            skills_data = json.loads(skills_str)
            if skills_data.get("status") != "success":
                raise Exception(f"指令 218 返回失敗狀態: {skills_data.get('message', '未知錯誤')}")
            
            skills = skills_data.get("data", [])
            
            if self.root.winfo_exists():
                def _show_dialog():
                    selected_id = self._show_skill_selection_dialog_and_get_id(name, skills)
                    if selected_id is not None:
                        # 找到技能名稱
                        skill_name = ""
                        for skill in skills:
                            if skill.get("skillID") == selected_id:
                                skill_name = skill.get("skillName", "")
                                break
                        callback(selected_id, skill_name)
                
                self.root.after(0, _show_dialog)
        
        except Exception as e:
            self.log_message(f"[{name}] 獲取或選擇技能時發生錯誤: {e}")
            self.handle_script_error(e, name)
        finally:
            if button and button.winfo_exists():
                self.root.after(0, lambda: button.config(state='normal'))
    
    def _save_and_close_general_afk_dialog(self, name, dialog):
        """儲存並關閉一般掛機對話框"""
        self.save_config()
        instance = self.instances[name]
        is_stop_on_map = instance["config"].get("general_afk_stop_on_map_change", False)
        status_text = "開啟" if is_stop_on_map else "關閉"
        self.log_message(f"[{name}] 已儲存一般掛機設定。 (離開地圖停止: {status_text})")
    
    def toggle_general_afk(self, name):
        """開始/停止一般掛機"""
        instance = self.instances[name]
        ui = instance["ui"]
        
        if instance["is_general_afk_running"]:
            # 停止掛機
            instance["is_general_afk_running"] = False
            self.log_message(f"[{name}] --- 正在停止一般掛機... ---")
            if "general_afk_toggle_button" in ui and ui["general_afk_toggle_button"].winfo_exists():
                ui["general_afk_toggle_button"].config(state='disabled', text="停止中...")
            if "general_afk_dialog_status_label" in ui and ui["general_afk_dialog_status_label"].winfo_exists():
                ui["general_afk_dialog_status_label"].config(text="一般掛機: 停止中...", foreground="gray")
            return
        
        if not instance.get("script_api"):
            return messagebox.showwarning(f"[{name}] 未連接", "請先點擊 '連接' 並等待RPC腳本載入成功。")
        
        # 只取得已啟用的技能
        all_buff_skills = instance["config"].get("general_afk_buff_skills", [])
        all_attack_skills = instance["config"].get("general_afk_attack_skills", [])
        
        buff_skills = [s for s in all_buff_skills if s.get("enabled", True)]
        attack_skills = [s for s in all_attack_skills if s.get("enabled", True)]
        
        if not buff_skills and not attack_skills:
            return messagebox.showwarning(f"[{name}] 未啟用技能", "請至少啟用一個 BUFF 技能或攻擊技能。")
        
        # 啟動掛機
        self.log_message(f"--- [{name}] 開始一般掛機 ---")
        if instance["config"].get("general_afk_stop_on_map_change", False):
            self.log_message(f"[{name}] 已啟用 '離開地圖後停止掛機'")
        self.log_message(f"[{name}] 已啟用 BUFF 技能數量: {len(buff_skills)}")
        self.log_message(f"[{name}] 已啟用攻擊技能數量: {len(attack_skills)}")
        
        instance["is_general_afk_running"] = True
        instance["buff_last_cast"] = {}
        instance["attack_last_cast"] = {}
        instance["general_afk_start_map_id"] = None # 重置起始地圖 ID
        
        if "general_afk_toggle_button" in ui and ui["general_afk_toggle_button"].winfo_exists():
            ui["general_afk_toggle_button"].config(text="停止掛機")
        
        if "general_afk_button" in ui and ui["general_afk_button"].winfo_exists():
            ui["general_afk_button"].config(text="掛機中", style='Red.Taller.TButton')
        
        # 啟動統一的掛機執行緒 (BUFF 優先)
        instance["general_afk_thread"] = threading.Thread(
            target=self.general_afk_unified_loop,
            args=(name, buff_skills, attack_skills),
            daemon=True
        )
        instance["general_afk_thread"].start()
    
    def general_afk_unified_loop(self, name, buff_skills, attack_skills):
        """統一的掛機迴圈 (BUFF 優先)"""
        instance = self.instances[name]
        api = instance["script_api"]
        
        try:
            while instance["is_general_afk_running"]:
                # ==================== 動態取得已啟用的技能 ====================
                # 在每次迴圈中重新取得,支援中途切換技能啟用狀態
                all_buff_skills = instance["config"].get("general_afk_buff_skills", [])
                all_attack_skills = instance["config"].get("general_afk_attack_skills", [])
                
                enabled_buff_skills = [s for s in all_buff_skills if s.get("enabled", True)]
                enabled_attack_skills = [s for s in all_attack_skills if s.get("enabled", True)]
                
                action_performed = False  # 標記本回合是否已執行動作 (施放 BUFF)
                current_status = "監控中" # Default status


                # 檢查是否需要 "離開地圖後停止"
                stop_on_map_change = instance["config"].get("general_afk_stop_on_map_change", False)
                start_map_id = instance.get("general_afk_start_map_id")


                # ==================== 優先檢查: 地圖變更與玩家狀態 ====================
                # 提前獲取玩家資訊 (201)，用於地圖檢查和後續的攻擊邏輯
                player_info = None
                try:
                    player_info_str = api.get_info(201)
                    if player_info_str:
                        player_data = json.loads(player_info_str)
                        player_info = player_data.get("data", player_data)
                        
                        # 檢查地圖變更
                        if stop_on_map_change:
                            current_map_id = player_info.get("mapId")
                            if current_map_id is None: # Fallback to mapName if mapId is missing
                                current_map_id = player_info.get("mapName")
                            
                            # 只有在成功獲取到地圖資料時才進行地圖變更檢查
                            if current_map_id is not None:
                                if start_map_id is None:
                                    instance["general_afk_start_map_id"] = current_map_id
                                    start_map_id = current_map_id
                                    self.log_message(f"[{name}] 記錄起始地圖: '{current_map_id}'")
                                elif current_map_id != start_map_id:
                                    self.log_message(f"[{name}] 偵測到地圖變更 (從 '{start_map_id}' 到 '{current_map_id}')。停止一般掛機。")
                                    self.toggle_general_afk(name) # Stop AFK
                                    break
                            else:
                                # 無法獲取地圖資料，跳過本次檢查（避免誤判）
                                pass
                except Exception as e:
                    self.log_message(f"[{name}] 獲取玩家資訊失敗: {e}")
                    # 如果連玩家資訊都拿不到，可能斷線或出錯，暫停一下避免死迴圈
                    time.sleep(1)
                    continue


                # ==================== 第一優先: BUFF 技能 ====================
                if enabled_buff_skills:
                    try:
                        buff_list_str = api.get_info(206)
                        if buff_list_str:
                            buff_data = json.loads(buff_list_str)
                            if buff_data.get("status") == "success":
                                current_buffs = buff_data.get("data", [])
                                
                                # 檢查並施放 BUFF
                                for buff_skill in enabled_buff_skills:
                                    if not instance["is_general_afk_running"]:
                                        break
                                    
                                    skill_id = buff_skill["skill_id"]
                                    last_cast_time = instance["buff_last_cast"].get(skill_id, 0)
                                    if time.time() - last_cast_time < buff_skill["cooldown"]:
                                        continue
                                    
                                    # 尋找對應的 BUFF
                                    current_buff = None
                                    for buff in current_buffs:
                                        if buff.get("buffID") == buff_skill["buff_id"]:
                                            current_buff = buff
                                            break
                                    
                                    should_cast = False
                                    
                                    # 條件 1: 檢查剩餘時間
                                    if buff_skill["check_time"] and current_buff:
                                        remain_time = current_buff.get("remainTime", 0) / 1000
                                        if remain_time <= buff_skill["time_threshold"]:
                                            should_cast = True
                                            self.log_message(f"[{name}] BUFF '{buff_skill['skill_name']}' 剩餘時間 {remain_time:.1f}s <= {buff_skill['time_threshold']}s,準備施放")
                                    
                                    # 條件 2: 檢查是否未擁有
                                    if buff_skill["check_missing"] and not current_buff:
                                        should_cast = True
                                        self.log_message(f"[{name}] 未擁有 BUFF '{buff_skill['skill_name']}',準備施放")
                                    
                                    # 施放技能
                                    if should_cast:
                                        try:
                                            result = api.use_skill(skill_id, "0")
                                            self.log_message(f"[{name}] 施放 BUFF 技能 '{buff_skill['skill_name']}' (ID:{skill_id})")
                                            current_status = f"施放: {buff_skill['skill_name']}"
                                            instance["buff_last_cast"][skill_id] = time.time()
                                            time.sleep(0.5)  # BUFF 施放後延遲
                                            action_performed = True # 標記已執行動作
                                            break # 嚴格優先: 一次只施放一個 BUFF，並跳過後續檢查
                                        except Exception as e:
                                            self.log_message(f"[{name}] 施放 BUFF 技能失敗: {e}")
                    
                    except Exception as e:
                        if instance["is_general_afk_running"]:
                            self.log_message(f"[{name}] BUFF 監控發生錯誤: {e}")
                
                # ==================== 第二優先: 攻擊技能 ====================
                # 只有在沒有執行任何 BUFF 動作時才執行攻擊
                if not action_performed and player_info:
                    try:
                        if enabled_attack_skills:
                            current_mp = player_info.get("curMP", 0)
                            max_mp = player_info.get("maxMP", 1)  # 避免除以零
                            mp_percent = int((current_mp / max_mp) * 100)
                            
                            # 獲取技能冷卻狀態
                            skills_info_str = api.get_info(218)
                            skills_data = json.loads(skills_info_str) if skills_info_str else {}
                            skills_list = skills_data.get("data", []) if skills_data.get("status") == "success" else []
                            
                            # 檢查並使用攻擊技能
                            for attack_skill in enabled_attack_skills:
                                if not instance["is_general_afk_running"]:
                                    break
                                
                                skill_id = attack_skill["skill_id"]
                                
                                # 檢查使用間隔
                                last_cast_time = instance["attack_last_cast"].get(skill_id, 0)
                                if time.time() - last_cast_time < attack_skill["interval"]:
                                    continue
                                
                                # 檢查 MP (百分比)
                                mp_condition = attack_skill.get("mp_condition", ">=")
                                
                                if mp_condition == ">=":
                                    if mp_percent < attack_skill["mp_threshold"]:
                                        continue
                                elif mp_condition == "<=":
                                    if mp_percent > attack_skill["mp_threshold"]:
                                        continue
                                
                                # 檢查技能冷卻
                                if attack_skill["check_cooldown"] and skills_list:
                                    skill_info = None
                                    for skill in skills_list:
                                        if skill.get("skillID") == skill_id:
                                            skill_info = skill
                                            break
                                    
                                    if skill_info and skill_info.get("cooldown", 0) > 0:
                                        continue
                                
                                # 使用技能
                                try:
                                    result = api.use_skill(skill_id, "0")
                                    #self.log_message(f"[{name}] 使用攻擊技能  '{attack_skill['skill_name']}'")
                                    current_status = f"施放: {attack_skill['skill_name']}"
                                    instance["attack_last_cast"][skill_id] = time.time()
                                    time.sleep(0.1)  # 攻擊技能之間延遲
                                except Exception as e:
                                    self.log_message(f"[{name}] 使用攻擊技能失敗: {e}")
                    
                    except Exception as e:
                        if instance["is_general_afk_running"]:
                            self.log_message(f"[{name}] 攻擊技能迴圈發生錯誤: {e}")
                
                # Update Status Label
                if self.root.winfo_exists() and "general_afk_dialog_status_label" in instance["ui"]:
                     cur_mp = player_info.get("curMP", 0) if player_info else 0
                     max_mp = player_info.get("maxMP", 1) if player_info else 1
                     if max_mp == 0: max_mp = 1
                     mp_percent = int((cur_mp / max_mp) * 100)
                     
                     label_text = f"MP: {mp_percent}% | {current_status}"
                     def _update_label():
                         if "general_afk_dialog_status_label" in instance["ui"] and instance["ui"]["general_afk_dialog_status_label"].winfo_exists():
                             instance["ui"]["general_afk_dialog_status_label"].config(text=label_text, foreground="blue")
                         if "general_afk_main_status_label" in instance["ui"] and instance["ui"]["general_afk_main_status_label"].winfo_exists():
                             instance["ui"]["general_afk_main_status_label"].config(text=label_text, foreground="blue")
                     self.root.after(0, _update_label)


                # ==================== 動態延遲計算 ====================
                min_wait_time = 0.5  # 預設最小延遲
                current_time = time.time()
                next_check_times = []
                
                # 1. 計算所有 BUFF 技能的剩餘冷卻時間
                for buff_skill in enabled_buff_skills:
                    skill_id = buff_skill["skill_id"]
                    last_cast = instance["buff_last_cast"].get(skill_id, 0)
                    cooldown = buff_skill.get("cooldown", 5)
                    
                    time_since_cast = current_time - last_cast
                    remaining = max(0, cooldown - time_since_cast)
                    
                    if remaining > 0:
                        next_check_times.append(remaining)
                
                # 2. 計算所有攻擊技能的剩餘冷卻時間
                for attack_skill in enabled_attack_skills:
                    skill_id = attack_skill["skill_id"]
                    last_cast = instance["attack_last_cast"].get(skill_id, 0)
                    interval = attack_skill.get("interval", 2)
                    
                    time_since_cast = current_time - last_cast
                    remaining = max(0, interval - time_since_cast)
                    
                    if remaining > 0:
                        next_check_times.append(remaining)
                
                # 3. 如果有任何攻擊技能啟用了遊戲內冷卻檢查，考慮 GCD
                check_game_cooldown = any(s.get("check_cooldown", False) for s in enabled_attack_skills)
                if check_game_cooldown and not action_performed:
                    try:
                        if 'skills_list' in locals() and skills_list:
                            for skill in skills_list:
                                game_cooldown_ms = skill.get("cooldown", 0)
                                if game_cooldown_ms > 0:
                                    # 將毫秒轉換為秒
                                    game_cooldown_sec = game_cooldown_ms / 1000.0
                                    next_check_times.append(game_cooldown_sec)
                                    break  # GCD 是全局的
                    except:
                        pass
                
                # 4. 計算最小等待時間
                if next_check_times:
                    min_wait_time = min(next_check_times)
                    min_wait_time = min_wait_time + 0.1  # 加上 0.1 秒緩衝
                    min_wait_time = max(0.1, min(min_wait_time, 15.0))  # 限制範圍
                    
                    # 只在延遲超過 0.1 秒時顯示 log
                    if min_wait_time >= 0.1:
                        #self.log_message(f"[{name}] ⏰ 等待 {min_wait_time:.1f}秒 ")                        
                        label_text = f"⏰ 等待 {min_wait_time:.1f}秒 "
                        def _update_label():
                            if "general_afk_dialog_status_label" in instance["ui"] and instance["ui"]["general_afk_dialog_status_label"].winfo_exists():
                                instance["ui"]["general_afk_dialog_status_label"].config(text=label_text, foreground="blue")
                            if "general_afk_main_status_label" in instance["ui"] and instance["ui"]["general_afk_main_status_label"].winfo_exists():
                                instance["ui"]["general_afk_main_status_label"].config(text=label_text, foreground="blue")
                        self.root.after(0, _update_label)
                
                time.sleep(min_wait_time)
        
        except Exception as e:
            if instance["is_general_afk_running"]:
                self.log_message(f"[{name}] 掛機迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] 一般掛機結束 ---")
            if self.root.winfo_exists() and name in self.instances:
                def _reset_ui():
                    if "general_afk_toggle_button" in instance["ui"] and instance["ui"]["general_afk_toggle_button"].winfo_exists():
                        instance["ui"]["general_afk_toggle_button"].config(state='normal', text="開始掛機")
                    if "general_afk_button" in instance["ui"] and instance["ui"]["general_afk_button"].winfo_exists():
                        instance["ui"]["general_afk_button"].config(text="一般掛機", style='Taller.TButton')
                    if "general_afk_dialog_status_label" in instance["ui"] and instance["ui"]["general_afk_dialog_status_label"].winfo_exists():
                        instance["ui"]["general_afk_dialog_status_label"].config(text="一般掛機: 未啟動", foreground="black")
                    if "general_afk_main_status_label" in instance["ui"] and instance["ui"]["general_afk_main_status_label"].winfo_exists():
                        instance["ui"]["general_afk_main_status_label"].config(text="未啟動", foreground="gray")
                self.root.after(0, _reset_ui)

    def general_afk_buff_loop(self, name, buff_skills):
        """BUFF 監控迴圈"""
        instance = self.instances[name]
        api = instance["script_api"]
        
        try:
            while instance["is_general_afk_running"]:
                # 獲取當前 BUFF 列表
                try:
                    buff_list_str = api.get_info(206)
                    if not buff_list_str:
                        time.sleep(1)
                        continue
                    
                    buff_data = json.loads(buff_list_str)
                    if buff_data.get("status") != "success":
                        time.sleep(1)
                        continue
                    
                    current_buffs = buff_data.get("data", [])
                    
                    # 除錯: 顯示當前所有 BUFF
                    if current_buffs:
                        buff_ids = [f"{b.get('buffID')}({b.get('buffName', '?')})" for b in current_buffs]
                        self.log_message(f"[{name}] 當前 BUFF 列表: {', '.join(buff_ids)}")
                    else:
                        self.log_message(f"[{name}] 當前沒有任何 BUFF")
                    
                    # 遍歷每個 BUFF 技能
                    for buff_skill in buff_skills:
                        if not instance["is_general_afk_running"]:
                            break
                        
                        # 檢查冷卻時間
                        skill_id = buff_skill["skill_id"]
                        last_cast_time = instance["buff_last_cast"].get(skill_id, 0)
                        if time.time() - last_cast_time < buff_skill["cooldown"]:
                            continue
                        
                        # 尋找對應的 BUFF
                        current_buff = None
                        for buff in current_buffs:
                            if buff.get("buffID") == buff_skill["buff_id"]:
                                current_buff = buff
                                break
                        
                        # 除錯: 顯示 BUFF 檢測結果
                        self.log_message(f"[{name}] 檢查 BUFF '{buff_skill['skill_name']}' (BUFF ID: {buff_skill['buff_id']}): {'找到' if current_buff else '未找到'}")
                        
                        should_cast = False
                        
                        # 條件 1: 檢查剩餘時間
                        if buff_skill["check_time"] and current_buff:
                            remain_time = current_buff.get("remainTime", 0) / 1000  # 轉換為秒
                            if remain_time <= buff_skill["time_threshold"]:
                                should_cast = True
                                self.log_message(f"[{name}] BUFF '{buff_skill['skill_name']}' 剩餘時間 {remain_time:.1f}s <= {buff_skill['time_threshold']}s,準備施放")
                        
                        # 條件 2: 檢查是否未擁有
                        if buff_skill["check_missing"] and not current_buff:
                            should_cast = True
                            self.log_message(f"[{name}] 未擁有 BUFF '{buff_skill['skill_name']}',準備施放")
                        
                        # 施放技能
                        if should_cast:
                            try:
                                result = api.use_skill(skill_id, "0")
                                self.log_message(f"[{name}] 施放 BUFF 技能 '{buff_skill['skill_name']}' (ID:{skill_id})")
                                instance["buff_last_cast"][skill_id] = time.time()
                                time.sleep(0.5)  # 技能之間稍微延遲
                            except Exception as e:
                                self.log_message(f"[{name}] 施放 BUFF 技能失敗: {e}")
                
                except Exception as e:
                    if instance["is_general_afk_running"]:
                        self.log_message(f"[{name}] BUFF 監控發生錯誤: {e}")
                
                time.sleep(1)  # 每秒檢查一次
        
        except Exception as e:
            if instance["is_general_afk_running"]:
                self.log_message(f"[{name}] BUFF 監控迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] BUFF 監控結束 ---")
            if self.root.winfo_exists() and name in self.instances:
                def _reset_ui():
                    if "general_afk_toggle_button" in instance["ui"] and instance["ui"]["general_afk_toggle_button"].winfo_exists():
                        instance["ui"]["general_afk_toggle_button"].config(state='normal', text="開始掛機")
                self.root.after(0, _reset_ui)
    
    def general_afk_attack_loop(self, name, attack_skills):
        """攻擊技能迴圈"""
        instance = self.instances[name]
        api = instance["script_api"]
        
        try:
            while instance["is_general_afk_running"]:
                try:
                    # 獲取當前 MP
                    player_info_str = api.get_info(201)
                    if not player_info_str:
                        time.sleep(0.5)
                        continue
                    
                    player_data = json.loads(player_info_str)
                    player_info = player_data.get("data", player_data)
                    current_mp = player_info.get("curMP", 0)
                    
                    # 獲取技能冷卻狀態
                    skills_info_str = api.get_info(218)
                    skills_data = json.loads(skills_info_str) if skills_info_str else {}
                    skills_list = skills_data.get("data", []) if skills_data.get("status") == "success" else []
                    
                    # 遍歷每個攻擊技能
                    for attack_skill in attack_skills:
                        if not instance["is_general_afk_running"]:
                            break
                        
                        skill_id = attack_skill["skill_id"]
                        
                        # 檢查使用間隔
                        last_cast_time = instance["attack_last_cast"].get(skill_id, 0)
                        if time.time() - last_cast_time < attack_skill["interval"]:
                            continue
                        
                        # 檢查 MP
                        if current_mp < attack_skill["mp_threshold"]:
                            continue
                        
                        # 檢查技能冷卻
                        if attack_skill["check_cooldown"] and skills_list:
                            skill_info = None
                            for skill in skills_list:
                                if skill.get("skillID") == skill_id:
                                    skill_info = skill
                                    break
                            
                            if skill_info and skill_info.get("cooldown", 0) > 0:
                                continue
                        
                        # 使用技能
                        try:
                            result = api.use_skill(skill_id, "0")
                            self.log_message(f"[{name}] 使用攻擊技能  '{attack_skill['skill_name']}' (ID:{skill_id})")
                            instance["attack_last_cast"][skill_id] = time.time()
                            time.sleep(0.1)  # 技能之間稍微延遲
                        except Exception as e:
                            self.log_message(f"[{name}] 使用攻擊技能失敗: {e}")
                
                except Exception as e:
                    if instance["is_general_afk_running"]:
                        self.log_message(f"[{name}] 攻擊技能迴圈發生錯誤: {e}")
                
                time.sleep(0.5)  # 每 0.5 秒檢查一次
                    
        except Exception as e:
            if instance["is_general_afk_running"]:
                self.log_message(f"[{name}] 攻擊技能迴圈發生嚴重錯誤: {e}")
                self.handle_script_error(e, name)
        finally:
            self.log_message(f"--- [{name}] 攻擊技能迴圈結束 ---")
            if self.root.winfo_exists() and name in self.instances:
                def _reset_ui():
                    if "general_afk_toggle_button" in instance["ui"] and instance["ui"]["general_afk_toggle_button"].winfo_exists():
                        instance["ui"]["general_afk_toggle_button"].config(state='normal', text="開始掛機")
                self.root.after(0, _reset_ui)

    # ==================== Frida 安裝功能 ====================
    
    def ensure_adb_device(self, name, adb_path, device_serial):
        """確保 adb 可正常連線到特定裝置，如果失敗會嘗試重新連線"""
        try:
            # 嘗試一次
            result = subprocess.run(
                [adb_path, "-s", device_serial, "shell", "echo ok"],
                capture_output=True, text=True, timeout=5
            )
            if "ok" in result.stdout:
                return True
        except:
            pass
        
        # 第一次失敗 → 檢查裝置列表
        self.log_message(f"[{name}] ADB 無法連線到裝置 {device_serial}，檢查裝置狀態...")
        
        try:
            # 檢查 adb devices 列表
            result = subprocess.run(
                [adb_path, "devices"],
                capture_output=True, text=True, timeout=5
            )
            
            device_found = False
            device_offline = False
            
            if result.stdout:
                for line in result.stdout.splitlines():
                    if device_serial in line:
                        device_found = True
                        if "offline" in line or "unauthorized" in line:
                            device_offline = True
                            self.log_message(f"[{name}] 裝置 {device_serial} 狀態異常: {line.strip()}")
                        break
            
            if not device_found:
                self.log_message(f"[{name}] ★ 在 adb devices 列表中找不到裝置: {device_serial}")
                self.log_message(f"[{name}] 可用裝置列表:")
                for line in result.stdout.splitlines():
                    if line.strip() and "List of devices" not in line:
                        self.log_message(f"[{name}]   - {line.strip()}")
                return False
            
            # 如果裝置離線，嘗試重新連線 (僅針對網路 ADB，如 IP:Port)
            if device_offline or ":" in device_serial:
                self.log_message(f"[{name}] 嘗試重新連線到裝置...")
                
                # 如果是網路裝置 (IP:Port 格式)，先斷開再重連
                if ":" in device_serial:
                    try:
                        subprocess.run([adb_path, "disconnect", device_serial], timeout=3)
                        time.sleep(0.5)
                        subprocess.run([adb_path, "connect", device_serial], timeout=5)
                        time.sleep(1)
                    except Exception as e:
                        self.log_message(f"[{name}] 重新連線失敗: {e}")
        
        except Exception as e:
            self.log_message(f"[{name}] 檢查裝置狀態失敗: {e}")
        
        # 再試一次
        try:
            result = subprocess.run(
                [adb_path, "-s", device_serial, "shell", "echo ok"],
                capture_output=True, text=True, timeout=5
            )
            if "ok" in result.stdout:
                self.log_message(f"[{name}] ✓ ADB 裝置連線成功")
                return True
        except:
            pass
        
        # 最後手段：如果還是失敗，詢問是否要重啟 ADB 服務 (會影響所有裝置)
        self.log_message(f"[{name}] ★ 無法連線到裝置: {device_serial}")
        self.log_message(f"[{name}] 提示: 如果問題持續，可能需要重啟 ADB 服務 (會影響所有裝置)")
        return False
    
    def install_frida_thread(self, name):
        """啟動 Frida 安裝執行緒"""
        thread = threading.Thread(target=self.install_frida_to_emulator, args=(name,), daemon=True)
        thread.start()
    
    def get_frida_server_path(self):
        """取得 frida-server 檔案路徑"""
        # 優先從設定檔讀取
        frida_path = self.config.get("global_settings", {}).get("frida_server_path", "")
        
        if frida_path and os.path.exists(frida_path):
            return frida_path
        
        # 預設路徑: 程式目錄下的 frida-server 資料夾
        default_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "frida-server", "frida-server"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "frida-server"),
            "./frida-server/frida-server",
            "./frida-server"
        ]
        
        for path in default_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def install_frida_to_emulator(self, name):
        """安裝 Frida Server 到模擬器"""
        try:
            instance = self.instances.get(name)
            if not instance:
                self.log_message(f"[{name}] 錯誤: 找不到模擬器實例")
                return
            
            ui = instance["ui"]
            adb_path = ui["adb_path_entry"].get().strip()
            device_serial = ui["device_serial_entry"].get().strip()
            
            if not adb_path or not device_serial:
                self.log_message(f"[{name}] 錯誤: 請先設定 ADB 路徑和裝置名稱")
                messagebox.showerror("設定錯誤", "請先填寫 ADB 路徑和裝置名稱 (Serial)")
                return
            
            # 檢查 frida-server 檔案
            frida_server_path = self.get_frida_server_path()
            if not frida_server_path:
                self.log_message(f"[{name}] 錯誤: 找不到 frida-server 檔案")
                self.log_message(f"[{name}] 請將 frida-server 檔案放置到以下任一位置:")
                self.log_message(f"[{name}]   - ./frida-server/frida-server")
                self.log_message(f"[{name}]   - ./frida-server")
                messagebox.showerror("檔案不存在", 
                    "找不到 frida-server 檔案!\n\n"
                    "請下載對應版本的 frida-server 並放置到:\n"
                    "  ./frida-server/frida-server\n\n"
                    "下載位置: https://github.com/frida/frida/releases")
                return
            
            # 檢查 ADB 裝置連線
            if not self.ensure_adb_device(name, adb_path, device_serial):
                messagebox.showerror("ADB 連線失敗", 
                    f"無法連線到裝置: {device_serial}\\n\\n"
                    "請確認:\\n"
                    "1. 模擬器已啟動\\n"
                    "2. ADB 路徑正確\\n"
                    "3. 裝置序號正確")
                return

            self.log_message(f"[{name}] ========== 開始安裝 Frida Server ==========")
            self.log_message(f"[{name}] 使用檔案: {frida_server_path}")
            
            # 步驟 1: 執行 adb root
            self.log_message(f"[{name}] 步驟 1/5: 取得 root 權限...")
            try:
                result = subprocess.run(
                    [adb_path, "-s", device_serial, "root"],
                    capture_output=True, text=True, timeout=10
                )
                self.log_message(f"[{name}] Root 權限: {result.stdout.strip() if result.stdout else '已取得'}")
            except Exception as e:
                self.log_message(f"[{name}] 警告: root 指令執行失敗 (可能已有 root 權限): {e}")
            
            time.sleep(1)
            
            # 步驟 2: 推送 frida-server 到模擬器
            self.log_message(f"[{name}] 步驟 2/5: 推送 frida-server 到模擬器...")
            try:
                result = subprocess.run(
                    [adb_path, "-s", device_serial, "push", frida_server_path, "/data/local/tmp/frida-server"],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    self.log_message(f"[{name}] 推送成功!")
                else:
                    self.log_message(f"[{name}] 推送失敗: {result.stderr}")
                    messagebox.showerror("推送失敗", f"無法推送 frida-server:\n{result.stderr}")
                    return
            except Exception as e:
                self.log_message(f"[{name}] 推送失敗: {e}")
                messagebox.showerror("推送失敗", f"推送過程發生錯誤:\n{e}")
                return
            
            # 步驟 3: 設定執行權限
            self.log_message(f"[{name}] 步驟 3/5: 設定執行權限...")
            try:
                result = subprocess.run(
                    [adb_path, "-s", device_serial, "shell", "chmod", "755", "/data/local/tmp/frida-server"],
                    capture_output=True, text=True, timeout=10
                )
                self.log_message(f"[{name}] 權限設定完成")
            except Exception as e:
                self.log_message(f"[{name}] 警告: 權限設定失敗: {e}")
            
            # 步驟 4: 檢查是否已在執行
            self.log_message(f"[{name}] 步驟 4/5: 檢查 frida-server 狀態...")
            try:
                result = subprocess.run(
                    [adb_path, "-s", device_serial, "shell", "pgrep", "frida-server"],
                    capture_output=True, text=True, timeout=10
                )
                if result.stdout.strip():
                    self.log_message(f"[{name}] frida-server 已在執行中 (PID: {result.stdout.strip()})")
                    self.log_message(f"[{name}] 停止舊的 frida-server...")
                    subprocess.run(
                        [adb_path, "-s", device_serial, "shell", "pkill", "frida-server"],
                        capture_output=True, text=True, timeout=10
                    )
                    time.sleep(1)
            except Exception as e:
                self.log_message(f"[{name}] 檢查狀態時發生錯誤: {e}")
            
            # 步驟 5: 啟動 frida-server
            self.log_message(f"[{name}] 步驟 5/5: 啟動 frida-server...")
            try:
                # 使用 Popen 在背景啟動 frida-server
                start_command = [adb_path, "-s", device_serial, "shell", "su", "-c", "/data/local/tmp/frida-server &"]
                subprocess.Popen(
                    start_command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(2)  # 等待啟動
                
                # 驗證是否成功啟動
                result = subprocess.run(
                    [adb_path, "-s", device_serial, "shell", "pgrep", "frida-server"],
                    capture_output=True, text=True, timeout=10
                )
                
                if result.stdout.strip():
                    pid = result.stdout.strip()
                    self.log_message(f"[{name}] ✓ 安裝成功! frida-server 正在執行 (PID: {pid})")
                    self.log_message(f"[{name}] ========================================")
                    messagebox.showinfo("安裝成功", 
                        f"Frida Server 已成功安裝並啟動!\n\n"
                        f"PID: {pid}\n"
                        f"裝置: {device_serial}")
                else:
                    self.log_message(f"[{name}] ✗ 啟動失敗: 無法找到 frida-server 進程")
                    self.log_message(f"[{name}] 請檢查模擬器是否有 root 權限")
                    messagebox.showerror("啟動失敗", "frida-server 啟動失敗\n請檢查模擬器是否有 root 權限")
                    
            except Exception as e:
                self.log_message(f"[{name}] 啟動失敗: {e}")
                messagebox.showerror("啟動失敗", f"啟動 frida-server 時發生錯誤:\n{e}")
                
        except Exception as e:
            self.log_message(f"[{name}] 安裝過程發生錯誤: {e}")
            messagebox.showerror("安裝失敗", f"安裝過程發生錯誤:\n{e}")
    
    def uninstall_frida_thread(self, name):
        """啟動 Frida 移除執行緒"""
        thread = threading.Thread(target=self.uninstall_frida_from_emulator, args=(name,), daemon=True)
        thread.start()
    
    def uninstall_frida_from_emulator(self, name):
        """從模擬器移除 Frida Server"""
        try:
            instance = self.instances.get(name)
            if not instance:
                self.log_message(f"[{name}] 錯誤: 找不到模擬器實例")
                return
            
            ui = instance["ui"]
            adb_path = ui["adb_path_entry"].get().strip()
            device_serial = ui["device_serial_entry"].get().strip()
            
            if not adb_path or not device_serial:
                self.log_message(f"[{name}] 錯誤: 請先設定 ADB 路徑和裝置名稱")
                messagebox.showerror("設定錯誤", "請先填寫 ADB 路徑和裝置名稱 (Serial)")
                return
            
            # 確認是否要移除
            confirm = messagebox.askyesno(
                "確認移除",
                f"確定要從 {device_serial} 移除 Frida Server 嗎?\n\n"
                "這將會:\n"
                "1. 停止正在執行的 frida-server\n"
                "2. 刪除 /data/local/tmp/frida-server 檔案"
            )
            
            if not confirm:
                self.log_message(f"[{name}] 使用者取消移除操作")
                return
            
            self.log_message(f"[{name}] ========== 開始移除 Frida Server ==========")
            
            # 步驟 1: 停止 frida-server
            self.log_message(f"[{name}] 步驟 1/2: 停止 frida-server 進程...")
            try:
                # 先檢查是否有在執行
                check_before = subprocess.run(
                    [adb_path, "-s", device_serial, "shell", "pgrep", "frida-server"],
                    capture_output=True, text=True, timeout=10
                )
                
                if check_before.stdout.strip():
                    self.log_message(f"[{name}] 發現 frida-server 正在執行 (PID: {check_before.stdout.strip()})")
                    
                    # 停止進程
                    result = subprocess.run(
                        [adb_path, "-s", device_serial, "shell", "su", "-c", "pkill frida-server"],
                        capture_output=True, text=True, timeout=10
                    )
                    
                    # 等待進程完全停止
                    time.sleep(2)
                    
                    # 驗證是否已停止
                    check_after = subprocess.run(
                        [adb_path, "-s", device_serial, "shell", "pgrep", "frida-server"],
                        capture_output=True, text=True, timeout=10
                    )
                    
                    if check_after.stdout.strip():
                        self.log_message(f"[{name}] ✗ 警告: frida-server 仍在執行 (PID: {check_after.stdout.strip()})")
                        self.log_message(f"[{name}] 嘗試強制終止...")
                        subprocess.run(
                            [adb_path, "-s", device_serial, "shell", "su", "-c", "pkill -9 frida-server"],
                            capture_output=True, text=True, timeout=10
                        )
                        time.sleep(1)
                    else:
                        self.log_message(f"[{name}] ✓ frida-server 已成功停止")
                else:
                    self.log_message(f"[{name}] frida-server 未在執行")
                    
            except Exception as e:
                self.log_message(f"[{name}] 停止進程時發生錯誤: {e}")
            
            # 步驟 2: 刪除檔案
            self.log_message(f"[{name}] 步驟 2/2: 刪除 frida-server 檔案...")
            try:
                # 先檢查檔案是否存在
                check_before = subprocess.run(
                    [adb_path, "-s", device_serial, "shell", "ls", "-l", "/data/local/tmp/frida-server"],
                    capture_output=True, text=True, timeout=10
                )
                
                if check_before.returncode == 0 and check_before.stdout.strip():
                    self.log_message(f"[{name}] 發現 frida-server 檔案,準備刪除...")
                    
                    # 方法 1: 嘗試一般刪除
                    result = subprocess.run(
                        [adb_path, "-s", device_serial, "shell", "rm", "/data/local/tmp/frida-server"],
                        capture_output=True, text=True, timeout=10
                    )
                    
                    if result.returncode != 0:
                        # 方法 2: 如果失敗,使用 root 權限刪除
                        self.log_message(f"[{name}] 一般刪除失敗,嘗試使用 root 權限...")
                        result = subprocess.run(
                            [adb_path, "-s", device_serial, "shell", "su", "-c", "rm /data/local/tmp/frida-server"],
                            capture_output=True, text=True, timeout=10
                        )
                    
                    time.sleep(1)
                    
                    # 驗證是否已刪除
                    check_after = subprocess.run(
                        [adb_path, "-s", device_serial, "shell", "ls", "/data/local/tmp/frida-server"],
                        capture_output=True, text=True, timeout=10
                    )
                    
                    # 檢查返回碼和錯誤訊息
                    if check_after.returncode != 0 or "No such file" in check_after.stderr:
                        self.log_message(f"[{name}] ✓ frida-server 檔案已成功刪除")
                        self.log_message(f"[{name}] ✓ 移除成功! frida-server 已完全移除")
                        self.log_message(f"[{name}] ========================================")
                        messagebox.showinfo("移除成功", 
                            f"Frida Server 已成功移除!\n\n"
                            f"裝置: {device_serial}")
                    else:
                        self.log_message(f"[{name}] ✗ 警告: 檔案仍然存在,嘗試最後手段...")
                        # 最後手段: 使用 root 強制刪除
                        force_result = subprocess.run(
                            [adb_path, "-s", device_serial, "shell", "su", "-c", "rm -rf /data/local/tmp/frida-server"],
                            capture_output=True, text=True, timeout=10
                        )
                        time.sleep(1)
                        
                        # 最後驗證
                        final_check = subprocess.run(
                            [adb_path, "-s", device_serial, "shell", "ls", "/data/local/tmp/frida-server"],
                            capture_output=True, text=True, timeout=10
                        )
                        
                        if final_check.returncode != 0 or "No such file" in final_check.stderr:
                            self.log_message(f"[{name}] ✓ frida-server 已強制刪除成功")
                            self.log_message(f"[{name}] ✓ 移除成功! frida-server 已完全移除")
                            self.log_message(f"[{name}] ========================================")
                            messagebox.showinfo("移除成功", 
                                f"Frida Server 已成功移除!\n\n"
                                f"裝置: {device_serial}")
                        else:
                            self.log_message(f"[{name}] ✗ 錯誤: 無法刪除檔案")
                            self.log_message(f"[{name}] 除錯資訊: returncode={final_check.returncode}")
                            self.log_message(f"[{name}] 除錯資訊: stdout={final_check.stdout}")
                            self.log_message(f"[{name}] 除錯資訊: stderr={final_check.stderr}")
                            messagebox.showerror("刪除失敗", 
                                "無法刪除 frida-server 檔案\n"
                                "可能檔案被鎖定或權限不足\n"
                                "請嘗試重啟模擬器後再試")
                else:
                    self.log_message(f"[{name}] frida-server 檔案不存在,無需刪除")
                    self.log_message(f"[{name}] ✓ 移除完成")
                    self.log_message(f"[{name}] ========================================")
                    messagebox.showinfo("移除完成", 
                        f"Frida Server 已移除!\n\n"
                        f"裝置: {device_serial}")
                    
            except Exception as e:
                self.log_message(f"[{name}] 刪除檔案時發生錯誤: {e}")
                messagebox.showerror("刪除失敗", f"刪除 frida-server 時發生錯誤:\n{e}")
                
        except Exception as e:
            self.log_message(f"[{name}] 移除過程發生錯誤: {e}")
            messagebox.showerror("移除失敗", f"移除過程發生錯誤:\n{e}")



    def open_follow_attack_dialog(self, name):
        """開啟跟隨攻擊設定對話框"""
        instance = self.instances[name]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"跟隨攻擊設定 - {name}")
        dialog.geometry("350x400")
        
        # 主要容器 Frame (用於統一背景色)
        main_frame = ttk.Frame(dialog, padding="5")
        main_frame.pack(expand=True, fill=tk.BOTH)
        
        # 目標選擇區
        target_frame = ttk.LabelFrame(main_frame, text="跟隨目標選擇", padding="5")
        target_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(target_frame, text="附近玩家列表:").pack(anchor='w')
        
        # 列表與捲動條
        list_frame = ttk.Frame(target_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=2)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        target_listbox = tk.Listbox(list_frame, height=8, yscrollcommand=scrollbar.set)
        target_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=target_listbox.yview)
        
        def refresh_targets():
            target_listbox.delete(0, tk.END)
            if not instance.get("script_api"):
                return
            
            try:
                # 呼叫 203 指令
                result_str = instance["script_api"].get_info(203)
                if not result_str:
                    return
                
                result = json.loads(result_str)
                data = result.get("data", [])
                
                # 過濾出玩家 (type=2)
                players = [obj for obj in data if obj.get("type") == 2]
                
                for p in players:
                    name = p.get("name", "Unknown")
                    pid = p.get("playerID", 0)
                    target_listbox.insert(tk.END, f"{name} ({pid})")
                    
            except Exception as e:
                print(f"Refresh targets error: {e}")

        refresh_btn = ttk.Button(target_frame, text="重新整理列表", command=refresh_targets)
        refresh_btn.pack(fill=tk.X, pady=2)
        
        # 參數設定區
        params_frame = ttk.LabelFrame(main_frame, text="參數設定", padding="5")
        params_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(params_frame, text="跟隨距離 (格):").grid(row=0, column=0, sticky='w', pady=2)
        dist_entry = ttk.Entry(params_frame, width=10)
        dist_entry.insert(0, str(instance["config"].get("follow_attack_distance", 3)))
        dist_entry.grid(row=0, column=1, sticky='w', padx=5)
        
        ttk.Label(params_frame, text="檢查間隔 (ms):").grid(row=1, column=0, sticky='w', pady=2)
        interval_entry = ttk.Entry(params_frame, width=10)
        interval_entry.insert(0, str(instance["config"].get("follow_attack_interval", 1000)))
        interval_entry.grid(row=1, column=1, sticky='w', padx=5)
        
        # 控制區
        control_frame = ttk.Frame(main_frame, padding="5")
        control_frame.pack(fill=tk.X, pady=2)
        
        status_label = ttk.Label(control_frame, text="狀態: 未啟動", foreground="gray")
        status_label.pack(pady=2)
        
        def start_follow():
            selection = target_listbox.curselection()
            if not selection:
                messagebox.showwarning("警告", "請先選擇一個跟隨目標")
                return
            
            selected_text = target_listbox.get(selection[0])
            # 解析 "Name (ID)"
            try:
                target_name = selected_text.split(" (")[0]
                target_id = int(selected_text.split("(")[1].strip(")"))
            except:
                messagebox.showerror("錯誤", "無法解析目標 ID")
                return
                
            try:
                dist = int(dist_entry.get())
                interval = int(interval_entry.get())
            except ValueError:
                messagebox.showerror("錯誤", "距離與間隔必須為整數")
                return
            
            # 儲存設定
            instance["config"]["follow_attack_distance"] = dist
            instance["config"]["follow_attack_interval"] = interval
            self.save_config()
            
            # 設定執行狀態
            instance["follow_attack_target_id"] = target_id
            instance["follow_attack_target_name"] = target_name
            instance["is_follow_attack_running"] = True
            
            # 啟動執行緒
            if instance["follow_attack_thread"] is None or not instance["follow_attack_thread"].is_alive():
                instance["follow_attack_thread"] = threading.Thread(target=self.follow_attack_thread, args=(name,), daemon=True)
                instance["follow_attack_thread"].start()
            
            status_label.config(text=f"正在跟隨: {target_name}", foreground="green")
            self.log_message(f"[{name}] 開始跟隨攻擊目標: {target_name} (ID: {target_id})")
            
        def stop_follow():
            instance["is_follow_attack_running"] = False
            status_label.config(text="狀態: 已停止", foreground="red")
            self.log_message(f"[{name}] 停止跟隨攻擊")

        start_btn = ttk.Button(control_frame, text="開始跟隨", command=start_follow)
        start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        stop_btn = ttk.Button(control_frame, text="停止跟隨", command=stop_follow)
        stop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        # 初始載入列表
        refresh_targets()
        
        # 如果正在執行，更新狀態顯示
        if instance.get("is_follow_attack_running"):
            t_name = instance.get("follow_attack_target_name", "Unknown")
            status_label.config(text=f"正在跟隨: {t_name}", foreground="green")

    def follow_attack_thread(self, name):
        """跟隨攻擊執行緒"""
        instance = self.instances[name]
        
        while instance.get("is_follow_attack_running"):
            try:
                api = instance.get("script_api")
                if not api:
                    time.sleep(1)
                    continue
                
                target_id = instance.get("follow_attack_target_id")
                dist_limit = instance["config"].get("follow_attack_distance", 3)
                interval = instance["config"].get("follow_attack_interval", 1000) / 1000.0
                
                # 取得自身資訊 (用於計算距離)
                my_info_str = api.get_info(201)
                my_x, my_y = None, None
                if my_info_str:
                    try:
                        j = json.loads(my_info_str)
                        if j.get("status") == "success":
                            d = j.get("data", {})
                            if isinstance(d, dict) and "x" in d:
                                my_x, my_y = d.get("x"), d.get("y")
                            else:
                                my_x, my_y = j.get("x"), j.get("y")
                    except: pass

                # 取得周圍物件
                objs_str = api.get_info(203)
                if not objs_str:
                    time.sleep(interval)
                    continue
                    
                objs_json = json.loads(objs_str)
                data = objs_json.get("data", [])
                
                # 尋找跟隨目標
                target_obj = next((obj for obj in data if obj.get("playerID") == target_id), None)
                
                if target_obj:
                    tx, ty = target_obj.get("x"), target_obj.get("y")
                    attack_id = target_obj.get("attackID", 0)
                    
                    # 1. 攻擊邏輯
                    if attack_id > 0:
                        # self.log_message(f"[{name}] 偵測到攻擊動作! 攻擊 ID: {attack_id}")
                        
                        # 尋找被攻擊的對象 (playerID 或 earthObjectID)
                        # 注意：怪物通常用 earthObjectID，玩家用 playerID
                        # 這裡假設 attackID 會對應到其中一個
                        attack_target = next((obj for obj in data if obj.get("playerID") == attack_id or obj.get("earthObjectID") == attack_id), None)
                        
                        if attack_target:
                            # 取得攻擊目標的 key
                            target_key = attack_target.get("objectKey")
                            target_name = attack_target.get("name", "Unknown")
                            target_id_val = attack_target.get("playerID") or attack_target.get("earthObjectID")
                            
                            # 檢查自己是否已經在攻擊該目標 (使用時間戳記防止重複指令)
                            last_target_id = instance.get("last_attack_target_id", 0)
                            last_attack_time = instance.get("last_attack_time", 0)
                            current_time = time.time()
                            
                            # 如果目標相同且距離上次攻擊不到 2 秒，則視為已經在攻擊
                            is_spamming = False
                            if last_target_id == target_id_val and (current_time - last_attack_time) < 2.0:
                                is_spamming = True
                            
                            if target_key and not is_spamming:
                                # 鎖定並攻擊
                                api.set_target(str(target_key)) # 轉成字串避免 JS 數字精度問題
                                # time.sleep(0.1) # 給予一點時間讓鎖定生效 (使用者測試後認為不需要延遲)
                                api.attack_pickup()
                                # self.log_message(f"[{name}] 跟隨攻擊 -> 鎖定目標: {target_name} (ID: {attack_id})")
                                
                                # 更新最後攻擊狀態
                                instance["last_attack_target_id"] = target_id_val
                                instance["last_attack_time"] = current_time
                                
                            elif is_spamming:
                                # 避免打斷攻擊動作
                                pass
                        else:
                             # self.log_message(f"[{name}] 找不到攻擊目標物件 (ID: {attack_id})")
                             pass
                    
                    # 2. 跟隨移動邏輯
                    if my_x is not None and my_y is not None and tx is not None and ty is not None:
                        dist = ((tx - my_x)**2 + (ty - my_y)**2)**0.5
                        
                        if dist > dist_limit:
                            api.moveto(tx, ty)
                            # print(f"[{name}] 跟隨移動: 距離 {dist:.1f} > {dist_limit}")
                
                else:
                    # 目標不在視野內，可能飛走了或太遠
                    # 這裡可以選擇是否要顯示警告，暫時保持安靜
                    pass
                    
            except Exception as e:
                print(f"[{name}] Follow attack error: {e}")
            
            time.sleep(interval)

if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except ImportError: pass
    style = ttk.Style(root)
    style.theme_use('clam')
    app = App(root, style)
    root.mainloop()