import customtkinter as ctk
from customtkinter import ThemeManager
from tkinter import messagebox
import os
import traceback
import ctypes
from ctypes import wintypes

from config import *
import config as config_module
from utils import resource_path

# Windows specific font loading
gdi32 = ctypes.WinDLL('gdi32')
gdi32.AddFontResourceW.argtypes = (wintypes.LPCWSTR,)
gdi32.AddFontResourceW.restype = wintypes.INT
gdi32.RemoveFontResourceW.argtypes = (wintypes.LPCWSTR,)
gdi32.RemoveFontResourceW.restype = wintypes.BOOL

HWND_BROADCAST = 0xFFFF
WM_FONTCHANGE = 0x001D
user32 = ctypes.WinDLL('user32')
user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = wintypes.LPARAM

class UIManager:
    def __init__(self, master, app_callbacks, log_callback, app_instance):
        self.master = master
        self.app_callbacks = app_callbacks
        self.log_callback = log_callback
        self.app = app_instance
        self._font_loaded_path = None
        
        self.log_callback(f"尝试配置字体: '{DESIRED_FONT_FAMILY}'. 若失败则回退到 '{DEFAULT_FALLBACK_FONT}'.")

        local_font_path = resource_path(DESIRED_FONT_FILENAME)

        font_successfully_registered = False
        if os.path.exists(local_font_path):
            self.log_callback(f"本地字体文件找到: {local_font_path}")
            try:
                ret = gdi32.AddFontResourceW(local_font_path)
                if ret > 0:
                    self.log_callback(f"Windows: 成功调用 AddFontResourceW 为 '{local_font_path}'. 返回: {ret} (加载的字体数).")
                    self._font_loaded_path = local_font_path # 保存路径以便卸载
                    user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
                    font_successfully_registered = True
                else:
                    self.log_callback(f"Windows: AddFontResourceW 调用失败，用于 '{local_font_path}'. 返回: {ret}. 将使用回退字体.", is_error=True)
            except Exception as e_load_win:
                self.log_callback(f"通过 AddFontResourceW 加载本地字体 '{local_font_path}' 时出错 (Windows): {e_load_win}. 将使用回退字体.", is_error=True)
        else:
            self.log_callback(f"本地字体文件 '{DESIRED_FONT_FILENAME}' 未找到于 '{local_font_path}'. 将使用回退字体 '{DEFAULT_FALLBACK_FONT}'.")

        if font_successfully_registered:
            config_module.DEFAULT_FALLBACK_FONT = DESIRED_FONT_FAMILY
            self.log_callback(f"已尝试注册/定位字体，将尝试使用字体家族: '{config_module.DEFAULT_FALLBACK_FONT}'.")
        else:
            self.log_callback(f"未成功注册/定位自定义字体，将使用回退字体: '{config_module.DEFAULT_FALLBACK_FONT}'.")

        if config_module.DEFAULT_FALLBACK_FONT == DESIRED_FONT_FAMILY:
            try:
                self.log_callback(f"尝试将 CustomTkinter 主题字体设置为: '{config_module.DEFAULT_FALLBACK_FONT}'")
                for widget_name in ThemeManager.theme:
                    if isinstance(ThemeManager.theme[widget_name], dict) and "font" in ThemeManager.theme[widget_name]:
                        original_font_tuple = ThemeManager.theme[widget_name]["font"]
                        if isinstance(original_font_tuple, (list, tuple)) and len(original_font_tuple) > 0:
                            new_font_list = list(original_font_tuple)
                            new_font_list[0] = config_module.DEFAULT_FALLBACK_FONT
                            ThemeManager.theme[widget_name]["font"] = tuple(new_font_list)
            except Exception as e_theme:
                self.log_callback(f"修改主题默认字体时出错: {e_theme}. CustomTkinter 将使用其默认字体或特定控件的备用字体.")
        
        self.log_callback(f"最终配置CTkFont时使用的字体家族: '{config_module.DEFAULT_FALLBACK_FONT}'")
        self.FONT_LABEL = ctk.CTkFont(family=config_module.DEFAULT_FALLBACK_FONT, size=FONT_SIZE_LABEL)
        self.FONT_TEXTBOX = ctk.CTkFont(family=config_module.DEFAULT_FALLBACK_FONT, size=FONT_SIZE_TEXTBOX)
        self.FONT_TITLE = ctk.CTkFont(family=config_module.DEFAULT_FALLBACK_FONT, size=FONT_SIZE_TITLE)
        self._setup_ui()

    def unload_custom_font(self):
        if not self._font_loaded_path:
            return
        try:
            ret = gdi32.RemoveFontResourceW(self._font_loaded_path)
            if ret:
                self.log_callback(f"Windows: 成功调用 RemoveFontResourceW 为 '{self._font_loaded_path}'.")
                user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
            else:
                self.log_callback(f"Windows: RemoveFontResourceW 调用失败，用于 '{self._font_loaded_path}'. GetLastError: {ctypes.get_last_error()}", is_warning=True)
            self._font_loaded_path = None
        except Exception as e:
            self.log_callback(f"卸载自定义字体时出错: {e}", is_error=True)

    def _do_log_to_ui_textbox_threadsafe(self, log_entry):
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            try:
                self.log_text.configure(state="normal")
                self.log_text.insert("end", log_entry + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            except Exception as e:
                print(f"[CRITICAL ERROR in _do_log_to_ui_textbox_threadsafe trying to log '{log_entry[:50]}...']: {e}")
                traceback.print_exc()
                try:
                    if self.log_text.winfo_exists():
                        self.log_text.configure(state="disabled")
                except:
                    pass

    def _setup_ui(self):
        self.master.title(APP_NAME)
        self.master.geometry(f"{INITIAL_WINDOW_WIDTH}x{INITIAL_WINDOW_HEIGHT}")
        self.master.resizable(False, False)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("dark-blue")

        self.main_frame = ctk.CTkFrame(self.master, corner_radius=0)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.top_info_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.top_info_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=(20, 5))
        self.top_info_frame.grid_columnconfigure(0, weight=1)
        self.top_info_frame.grid_columnconfigure(1, weight=1)

        self.local_frame = ctk.CTkFrame(self.top_info_frame)
        self.local_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)
        self.local_frame.grid_columnconfigure(0, weight=0)
        self.local_frame.grid_columnconfigure(1, weight=1)
        local_title = ctk.CTkLabel(self.local_frame, text="本机", font=self.FONT_TITLE, anchor="center")
        local_title.grid(row=0, column=0, columnspan=2, pady=(0,10), sticky="ew")
        
        self.lbl_local_ip_text = ctk.CTkLabel(self.local_frame, text="IP地址:", font=self.FONT_LABEL)
        self.lbl_public_ip = ctk.CTkLabel(self.local_frame, text="N/A", anchor="w", font=self.FONT_LABEL)
        self.lbl_local_port_text = ctk.CTkLabel(self.local_frame, text="端口号:", font=self.FONT_LABEL)
        self.lbl_public_port = ctk.CTkLabel(self.local_frame, text="N/A", anchor="w", font=self.FONT_LABEL)
        self.lbl_feature_code_text = ctk.CTkLabel(self.local_frame, text="一次性特征码:", font=self.FONT_LABEL)
        self.lbl_feature_code_text = ctk.CTkLabel(self.local_frame, text="一次性特征码:", font=self.FONT_LABEL)
        self.feature_code_wrapper_frame = ctk.CTkFrame(self.local_frame, corner_radius=8, border_width=1, border_color=("gray75", "gray25"))
        self.feature_code_wrapper_frame.configure(height=32)
        self.feature_code_wrapper_frame.grid_propagate(False)
        self.feature_code_wrapper_frame.grid_columnconfigure(0, weight=1)
        self.lbl_feature_code = ctk.CTkLabel(self.feature_code_wrapper_frame, text="N/A", anchor="center", cursor="hand2", font=self.FONT_LABEL)
        self.lbl_feature_code.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        self.lbl_feature_code.bind("<Button-1>", lambda e: self.app_callbacks["ui_on_copy_feature_code"]())

        self.peer_frame = ctk.CTkFrame(self.top_info_frame)
        self.peer_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)
        self.peer_frame.grid_columnconfigure(0, weight=0)
        self.peer_frame.grid_columnconfigure(1, weight=1)
        peer_title = ctk.CTkLabel(self.peer_frame, text="远端", font=self.FONT_TITLE, anchor="center")
        peer_title.grid(row=0, column=0, columnspan=2, pady=(0,38), sticky="ew")
        self.lbl_remote_ip_text = ctk.CTkLabel(self.peer_frame, text="IP 地址:", font=self.FONT_LABEL)
        self.ent_peer_ip = ctk.CTkEntry(self.peer_frame, font=self.FONT_LABEL, placeholder_text="可由特征码解析")
        self.ent_peer_ip.bind("<KeyRelease>", lambda event: self.app_callbacks["ui_on_peer_info_changed"]())
        self.lbl_remote_port_text = ctk.CTkLabel(self.peer_frame, text="端口号:", font=self.FONT_LABEL)
        self.ent_peer_port = ctk.CTkEntry(self.peer_frame, font=self.FONT_LABEL, placeholder_text="可由特征码解析")
        self.ent_peer_port.bind("<KeyRelease>", lambda event: self.app_callbacks["ui_on_peer_info_changed"]())
        self.btn_parse_feature_code = ctk.CTkButton(self.peer_frame, text="粘贴一次性特征码", width=200, command=self.app_callbacks["ui_on_paste_feature_code"], font=self.FONT_LABEL, height=32)
        current_row_main = 2

        status_title_label = ctk.CTkLabel(self.main_frame, text="通话状态", font=self.FONT_TITLE)
        status_title_label.grid(row=current_row_main, column=0, pady=(20,5), sticky="w")
        current_row_main += 1

        status_indicator_display_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        status_indicator_display_frame.grid(row=current_row_main, column=0, padx=5, pady=(0,10), sticky="ew")
        status_indicator_display_frame.grid_columnconfigure(0, weight=1) # For status labels
        status_indicator_display_frame.grid_columnconfigure(1, weight=0) # For packet indicator

        self.lbl_status = ctk.CTkLabel(status_indicator_display_frame, text="正在启动...", font=ctk.CTkFont(family=config_module.DEFAULT_FALLBACK_FONT, size=FONT_SIZE_STATUS), anchor="w")
        self.lbl_status.grid(row=0, column=0, sticky="w")

        self.multi_part_status_frame = ctk.CTkFrame(status_indicator_display_frame, fg_color="transparent")

        self.status_font = ctk.CTkFont(family=config_module.DEFAULT_FALLBACK_FONT, size=FONT_SIZE_STATUS)
        self.lbl_status_part1 = ctk.CTkLabel(self.multi_part_status_frame, text="", font=self.status_font, anchor="w")
        self.lbl_status_part1.pack(side="left", padx=0, pady=0)

        self.lbl_status_separator = ctk.CTkLabel(self.multi_part_status_frame, text="", font=self.status_font, anchor="w")
        self.lbl_status_separator.pack(side="left", padx=0, pady=0)

        self.lbl_status_part3 = ctk.CTkLabel(self.multi_part_status_frame, text="", font=self.status_font, anchor="w")
        self.lbl_status_part3.pack(side="left", padx=0, pady=0)
        
        self.multi_part_status_frame.grid_remove() # Start hidden
        self.packet_status_indicator = ctk.CTkLabel(
            status_indicator_display_frame,
            text="",
            width=40,
            height=24,
            corner_radius=6,
            fg_color=PACKET_INDICATOR_IDLE
        )
        self.packet_status_indicator.grid(row=0, column=1, padx=(10,0), sticky="e")
        current_row_main += 1

        self.call_actions_row = current_row_main
        
        self.btn_call_hangup = ctk.CTkButton(self.main_frame, text="呼叫", command=self.app_callbacks["ui_on_call_hangup_button_clicked"], state="disabled", font=self.FONT_LABEL)
        self.default_button_color = self.btn_call_hangup.cget("fg_color")
        self.default_button_text_color = self.btn_call_hangup.cget("text_color")
        self.default_button_hover_color = self.btn_call_hangup.cget("hover_color")


        self.accept_reject_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.accept_reject_frame.grid_columnconfigure(0, weight=1)
        self.accept_reject_frame.grid_columnconfigure(1, weight=1)

        self.btn_accept_call = ctk.CTkButton(
            self.accept_reject_frame,
            text="接听",
            command=self.app_callbacks["ui_on_accept_call"],
            font=self.FONT_LABEL,
            fg_color=COLOR_BUTTON_ACCEPT_BG,
            hover_color=COLOR_BUTTON_ACCEPT_HOVER_BG,
            text_color=COLOR_BUTTON_CALL_FG
        )
        self.btn_accept_call.grid(row=0, column=0, padx=(0, 5), pady=0, sticky="ew")

        self.btn_reject_call = ctk.CTkButton(
            self.accept_reject_frame,
            text="拒绝",
            command=self.app_callbacks["ui_on_reject_call"],
            font=self.FONT_LABEL,
            fg_color=COLOR_BUTTON_REJECT_BG,
            hover_color=COLOR_BUTTON_REJECT_HOVER_BG,
            text_color=COLOR_BUTTON_CALL_FG
        )
        self.btn_reject_call.grid(row=0, column=1, padx=(5, 0), pady=0, sticky="ew")

        self.accept_reject_frame.grid_remove()
        self.btn_call_hangup.grid(row=self.call_actions_row, column=0, padx=5, pady=5, sticky="ew")
        current_row_main += 1

        mute_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        mute_frame.grid(row=current_row_main, column=0, pady=(5,10), sticky="ew")
        mute_frame.grid_columnconfigure(0, weight=0)
        mute_frame.grid_columnconfigure(1, weight=0)
        mute_frame.grid_columnconfigure(2, weight=1)
        mute_frame.grid_columnconfigure(3, weight=0)

        self.switch_mic_mute = ctk.CTkSwitch(mute_frame, text="麦克风: 开", command=self.app_callbacks["ui_on_toggle_mic"], font=self.FONT_LABEL)
        self.switch_mic_mute.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.switch_mic_mute.select()

        self.switch_speaker_mute = ctk.CTkSwitch(mute_frame, text="扬声器: 开", command=self.app_callbacks["ui_on_toggle_speaker"], font=self.FONT_LABEL)
        self.switch_speaker_mute.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.switch_speaker_mute.select()
        
        self.dev_mode_switch = ctk.CTkSwitch(mute_frame, text="DEV 模式", command=self.app_callbacks["ui_on_toggle_dev_mode"], font=self.FONT_LABEL)
        self.dev_mode_switch.grid(row=0, column=3, padx=5, pady=5, sticky="e")
        current_row_main += 1

        self.log_display_frame_row = current_row_main
        self.log_display_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.log_display_frame.grid_rowconfigure(0, weight=1)
        self.log_display_frame.grid_columnconfigure(0, weight=1)
        self.log_text = ctk.CTkTextbox(self.log_display_frame, state="disabled", wrap="word", font=self.FONT_TEXTBOX)

        self.update_dev_mode_visibility(False)

    def update_dev_mode_visibility(self, dev_mode_enabled):
        target_height = INITIAL_WINDOW_HEIGHT
        if dev_mode_enabled:
            target_height += DEV_MODE_HEIGHT_INCREASE
        
        if self.master.winfo_exists():
            self.master.geometry(f"{INITIAL_WINDOW_WIDTH}x{target_height}")

        dev_widgets = [
            self.lbl_local_ip_text, self.lbl_public_ip,
            self.lbl_local_port_text, self.lbl_public_port,
            self.lbl_remote_ip_text, self.ent_peer_ip,
            self.lbl_remote_port_text, self.ent_peer_port
        ]
        for widget in dev_widgets:
            if widget.winfo_exists() and widget.winfo_ismapped():
                 widget.grid_remove()

        lf_current_row = 1
        self.lbl_feature_code_text.grid(row=lf_current_row, column=0, columnspan=2, sticky="w", padx=5, pady=(5,0))
        lf_current_row += 1
        self.feature_code_wrapper_frame.grid(row=lf_current_row, column=0, columnspan=2, sticky="ew", padx=5, pady=(0,5))
        lf_current_row += 1

        if dev_mode_enabled:
            self.lbl_local_ip_text.grid(row=lf_current_row, column=0, sticky="w", padx=5, pady=2)
            self.lbl_public_ip.grid(row=lf_current_row, column=1, sticky="ew", padx=5, pady=2)
            lf_current_row += 1
            self.lbl_local_port_text.grid(row=lf_current_row, column=0, sticky="w", padx=5, pady=2)
            self.lbl_public_port.grid(row=lf_current_row, column=1, sticky="ew", padx=5, pady=2)

        pf_current_row = 1
        self.btn_parse_feature_code.grid(row=pf_current_row, column=0, columnspan=2, padx=5, pady=(5, 5), sticky="ew")
        pf_current_row +=1

        if dev_mode_enabled:
            self.lbl_remote_ip_text.grid(row=pf_current_row, column=0, sticky="w", padx=5, pady=2)
            self.ent_peer_ip.grid(row=pf_current_row, column=1, sticky="ew", padx=5, pady=2)
            pf_current_row += 1
            self.lbl_remote_port_text.grid(row=pf_current_row, column=0, sticky="w", padx=5, pady=2)
            self.ent_peer_port.grid(row=pf_current_row, column=1, sticky="ew", padx=5, pady=2)

        if dev_mode_enabled:
            self.log_display_frame.configure(height=150) 
            self.log_display_frame.grid_propagate(False) 
            self.log_display_frame.grid(row=self.log_display_frame_row, column=0, padx=5, pady=(10,5), sticky="nsew")

            if hasattr(self, 'log_text') and self.log_text.winfo_exists():
                self.log_text.configure(font=self.FONT_TEXTBOX)
            
            self.log_text.grid(row=0, column=0, sticky="nsew")
            
            if self.main_frame.winfo_exists():
                self.main_frame.grid_rowconfigure(self.log_display_frame_row, weight=1)

        else: 
            if self.log_text.winfo_exists() and self.log_text.winfo_ismapped():
                self.log_text.grid_remove()
            if self.log_display_frame.winfo_exists() and self.log_display_frame.winfo_ismapped():
                self.log_display_frame.grid_remove()
            if self.main_frame.winfo_exists():
                self.main_frame.grid_rowconfigure(self.log_display_frame_row, weight=0)

        if "ui_force_peer_field_update" in self.app_callbacks:
            self.app_callbacks["ui_force_peer_field_update"]()

    def log_to_ui_textbox(self, log_entry, is_dev_mode):
        if is_dev_mode and hasattr(self, 'log_text') and self.master.winfo_exists():
            self.master.after(0, self._do_log_to_ui_textbox_threadsafe, log_entry)

    def _set_label_text_threadsafe(self, label_widget, text_to_set):
        if hasattr(label_widget, 'winfo_exists') and label_widget.winfo_exists():
            label_widget.configure(text=text_to_set)
    
    def set_local_ip_port_display(self, public_ip_text, public_port_text):
        if hasattr(self, 'lbl_public_ip') and self.master.winfo_exists(): # Check master
            self.master.after(0, self._set_label_text_threadsafe, self.lbl_public_ip, public_ip_text)
        if hasattr(self, 'lbl_public_port') and self.master.winfo_exists(): # Check master
            self.master.after(0, self._set_label_text_threadsafe, self.lbl_public_port, public_port_text)

    def set_feature_code_display(self, feature_code_text):
        if hasattr(self, 'lbl_feature_code') and self.master.winfo_exists(): # Check master
            self.master.after(0, self._set_label_text_threadsafe, self.lbl_feature_code, feature_code_text)

    def get_peer_ip_entry(self):
        return self.ent_peer_ip.get() if hasattr(self, 'ent_peer_ip') and self.ent_peer_ip.winfo_exists() else ""

    def get_peer_port_entry(self):
        return self.ent_peer_port.get() if hasattr(self, 'ent_peer_port') and self.ent_peer_port.winfo_exists() else ""

    def set_peer_ip_entry(self, ip):
        if hasattr(self, 'ent_peer_ip') and self.ent_peer_ip.winfo_exists():
            current_state = self.ent_peer_ip.cget("state")
            if current_state == "disabled": self.ent_peer_ip.configure(state="normal")
            self.ent_peer_ip.delete(0, "end")
            self.ent_peer_ip.insert(0, ip)
            if current_state == "disabled": self.ent_peer_ip.configure(state="disabled")

    def set_peer_port_entry(self, port):
        if hasattr(self, 'ent_peer_port') and self.ent_peer_port.winfo_exists():
            current_state = self.ent_peer_port.cget("state")
            if current_state == "disabled": self.ent_peer_port.configure(state="normal")
            self.ent_peer_port.delete(0, "end")
            self.ent_peer_port.insert(0, str(port))
            if current_state == "disabled": self.ent_peer_port.configure(state="disabled")

    def update_status_label(self, message, color=None):
        if not (hasattr(self, 'lbl_status') and self.lbl_status.winfo_exists()):
            return

        receive_status_app_attr = getattr(self.app, 'can_reliably_receive_calls', None)

        is_special_status_waiting = (message == STATUS_WAITING_FOR_REMOTE_INFO)
        is_special_status_ready = (message == STATUS_READY_TO_CALL_OR_RECEIVE)

        if is_special_status_waiting or is_special_status_ready:
            if self.lbl_status.winfo_ismapped():
                self.lbl_status.grid_remove()
            if not self.multi_part_status_frame.winfo_ismapped():
                self.multi_part_status_frame.grid(row=0, column=0, sticky="w", in_=self.lbl_status.master)

            receive_text = ""
            receive_color = COLOR_STATUS_DEFAULT

            if receive_status_app_attr is None:
                receive_text = "NAT可接收性检测中..."
                receive_color = COLOR_STATUS_INFO
            elif receive_status_app_attr is True:
                receive_text = "已可接收呼叫"
                receive_color = COLOR_STATUS_SUCCESS
            elif receive_status_app_attr is False:
                receive_text = "无法接收呼叫（您的网络条件不符）"
                receive_color = COLOR_STATUS_ERROR

            if is_special_status_waiting:
                self.lbl_status_part1.configure(text="未有远端特征", text_color=COLOR_STATUS_ERROR)
                self.lbl_status_separator.configure(text=" | ", text_color=COLOR_TEXT_DEFAULT)
                self.lbl_status_part3.configure(text=receive_text, text_color=receive_color)
            elif is_special_status_ready:
                self.lbl_status_part1.configure(text="已可发出呼叫", text_color=COLOR_STATUS_SUCCESS)
                self.lbl_status_separator.configure(text=" | ", text_color=COLOR_TEXT_DEFAULT)
                self.lbl_status_part3.configure(text=receive_text, text_color=receive_color)
        else:
            if self.multi_part_status_frame.winfo_ismapped():
                self.multi_part_status_frame.grid_remove()
            if not self.lbl_status.winfo_ismapped():
                self.lbl_status.grid(row=0, column=0, sticky="w", in_=self.multi_part_status_frame.master)

            final_color = color if color is not None else COLOR_STATUS_DEFAULT
            self.lbl_status.configure(text=f"{message}", text_color=final_color)
            
    def update_packet_indicator(self, color=None):
        final_color = color if color is not None else PACKET_INDICATOR_IDLE
        if hasattr(self, 'packet_status_indicator') and self.packet_status_indicator.winfo_exists():
            try:
                current_fg_tuple = self.packet_status_indicator.cget("fg_color")
                current_fg_actual = current_fg_tuple[0] if isinstance(current_fg_tuple, (list,tuple)) else current_fg_tuple

                if str(current_fg_actual).lower() != str(final_color).lower():
                    self.packet_status_indicator.configure(fg_color=final_color)
            except Exception as e:
                self.log_callback(f"Error updating packet indicator (CTkLabel): {e}")


    def set_call_button_mode(self, mode: str):
        if not (hasattr(self.master, 'winfo_exists') and self.master.winfo_exists()):
            return

        if mode == "accept_reject":
            if self.btn_call_hangup.winfo_ismapped():
                self.btn_call_hangup.grid_remove()
            if not self.accept_reject_frame.winfo_ismapped():
                self.accept_reject_frame.grid(row=self.call_actions_row, column=0, padx=5, pady=5, sticky="ew")
        elif mode == "single":
            if self.accept_reject_frame.winfo_ismapped():
                self.accept_reject_frame.grid_remove()
            if not self.btn_call_hangup.winfo_ismapped():
                self.btn_call_hangup.grid(row=self.call_actions_row, column=0, padx=5, pady=5, sticky="ew")
        else:
            self.log_callback(f"Unknown call button mode: {mode}", is_warning=True)

    def configure_call_button(self, text, command, fg_color, hover_color, text_color, state):
        if hasattr(self, 'btn_call_hangup') and self.btn_call_hangup.winfo_exists():
            self.btn_call_hangup.configure(
                text=text, command=command,
                fg_color=fg_color,
                hover_color=hover_color,
                text_color=text_color,
                state=state
            )
    
    def configure_peer_input_fields(self, ip_entry_state, port_entry_state, parse_btn_state):
        if hasattr(self, 'ent_peer_ip') and self.ent_peer_ip.winfo_exists():
            self.ent_peer_ip.configure(state=ip_entry_state)
        if hasattr(self, 'ent_peer_port') and self.ent_peer_port.winfo_exists():
            self.ent_peer_port.configure(state=port_entry_state)
        if hasattr(self, 'btn_parse_feature_code') and self.btn_parse_feature_code.winfo_exists():
            self.btn_parse_feature_code.configure(state=parse_btn_state)

    def update_mute_switch_text(self, mic_muted, speaker_switch_is_off):
        if hasattr(self, 'switch_mic_mute') and self.switch_mic_mute.winfo_exists():
            self.switch_mic_mute.configure(text="麦克风: 静音" if mic_muted else "麦克风: 开")
        if hasattr(self, 'switch_speaker_mute') and self.switch_speaker_mute.winfo_exists():
            self.switch_speaker_mute.configure(text="扬声器: 关闭" if speaker_switch_is_off else "扬声器: 开")
            
    def show_message(self, title, message, type="info"):
        if not (hasattr(self.master, 'winfo_exists') and self.master.winfo_exists()): return None
        if type == "info": return messagebox.showinfo(title, message, parent=self.master)
        if type == "warning": return messagebox.showwarning(title, message, parent=self.master)
        if type == "error": return messagebox.showerror(title, message, parent=self.master)
        if type == "askyesno": return messagebox.askyesno(title, message, parent=self.master)
        if type == "askretrycancel": return messagebox.askretrycancel(title, message, parent=self.master)
        return None

    def get_clipboard_data(self):
        try:
            return self.master.clipboard_get()
        except Exception:
            return None 

    def set_clipboard_data(self, text):
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(text)
            return True
        except Exception:
            return False