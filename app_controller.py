import customtkinter as ctk
import threading
import datetime
import os
import locale
import time

from config import *
from models import AppState
from utils import resource_path, FeatureCodeManager, SingleThreadPreciseTimer
from audio_manager import AudioManager
from network_manager import NetworkManager
from ui_manager import UIManager
from state_manager import CallStateManager
from event_handler import EventHandler
from ui_handler import UIStateHandler

class AppController:
    def __init__(self, master_tk_root: ctk.CTk):
        self.master = master_tk_root
        self._is_closing = False
        self.is_running_main_op = False
        self.dev_mode_enabled = False
        self.feature_code_manager = FeatureCodeManager(FEATURE_CODE_KEY)
        self.feature_code_str = "N/A"
        self.can_reliably_receive_calls = None

        self.indicator_blinker_timer = SingleThreadPreciseTimer(self.master, name="IndicatorBlinkerThread")

        self.audio_manager = AudioManager(
            log_callback=lambda msg, **kwargs: self.log_message(msg, "Audio", **kwargs),
            deduplication_callback=self._handle_audio_deduplication
        )
        self.network_manager = NetworkManager(log_callback=lambda msg, **kwargs: self.log_message(msg, "Network", **kwargs))
        
        self.state_manager = CallStateManager(
            master_ref=self.master, 
            audio_manager_ref=self.audio_manager, 
            network_manager_ref=self.network_manager, 
            state_change_callback=self._on_state_changed, 
            log_callback=lambda msg, **kwargs: self.log_message(msg, "State", **kwargs)
        )
        
        self.ui_manager = UIManager(
            master_tk_root, 
            app_callbacks={}, 
            log_callback=lambda msg, **kwargs: self.log_message(msg, "UI", **kwargs), 
            app_instance=self
        )
        
        self.event_handler = EventHandler(
            controller_ref=self,
            state_manager_ref=self.state_manager,
            ui_manager_ref=self.ui_manager,
            audio_manager_ref=self.audio_manager,
            log_callback=lambda msg, **kwargs: self.log_message(msg, "Event", **kwargs)
        )
        
        self.ui_handler = UIStateHandler(
            ui_manager_ref=self.ui_manager, 
            state_manager_ref=self.state_manager, 
            controller_ref=self
        )

        self.network_manager.data_received_callback = self.event_handler.on_network_data_received
        
        self.ui_manager.app_callbacks = self.event_handler.get_ui_callbacks()
        if hasattr(self.ui_manager, '_assign_callbacks'):
            self.ui_manager._assign_callbacks()

        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._start_full_initialization_threaded()

    def _on_state_changed(self, new_state: AppState, reason: str, peer_address_tuple, associated_data):
        self.ui_handler.update_ui_elements_for_state(new_state, reason, peer_address_tuple, associated_data)

    def log_message(self, message, source="Controller", is_error=False, is_warning=False):
        now = datetime.datetime.now()
        formatted_time = now.strftime('%H:%M:%S') + f".{now.microsecond // 1000:03d}"
        state_name = self.state_manager.app_state.name if hasattr(self, 'state_manager') else "UNSET"
        log_level = "ERROR" if is_error else "WARN" if is_warning else "INFO"
        log_entry = f"{formatted_time} [{state_name}] [{source}] [{log_level}] - {message}"
        print(log_entry)
        if hasattr(self, 'ui_manager'):
            self.ui_manager.log_to_ui_textbox(log_entry, self.dev_mode_enabled)

    def _start_full_initialization_threaded(self):
        self.state_manager.set_app_state(AppState.INITIALIZING_NETWORK, "正在后台初始化网络和服务...")
        threading.Thread(target=self._perform_full_initialization_flow, daemon=True).start()

    def _perform_full_initialization_flow(self):
        audio_init_success = self.audio_manager.initialize_pyaudio_core()
        network_init_success, network_msg = self.network_manager.start_listening_and_stun()
        
        if not audio_init_success:
            self.state_manager.set_app_state(AppState.CALL_ENDED_ERROR, "PyAudio核心初始化失败，应用无法使用。")
            if self.master.winfo_exists():
                self.master.after(0, lambda: self.ui_manager.show_message("严重错误", "PyAudio核心初始化失败。\n请检查音频设备和驱动程序。", type="error"))
            return

        if network_init_success:
            self.is_running_main_op = True
            if self.master.winfo_exists():
                self.master.after(0, lambda: self.ui_manager.set_local_ip_port_display(self.network_manager.public_ip, str(self.network_manager.public_port)))
                self.master.after(0, self.generate_and_update_feature_code)
                self.master.after(0, lambda: self.state_manager.set_app_state(AppState.IDLE, "初始化完成，应用已就绪。"))

            threading.Thread(target=self._perform_nat_test_in_background, daemon=True, name="NatTestThread").start()
        else:
            if self.master.winfo_exists():
                error_reason = network_msg or "获取公网IP或启动监听失败，请检查网络。"
                self.master.after(0, lambda: self.state_manager.set_app_state(AppState.GETTING_PUBLIC_IP_FAILED, error_reason))
                self.master.after(0, lambda: self.ui_manager.set_local_ip_port_display(self.network_manager.public_ip or "获取失败", "N/A"))

    def _perform_nat_test_in_background(self):
        self.log_message("开始后台NAT开放性测试...")
        nat_test_passed = self.network_manager.check_nat_openness_for_unsolicited_responses()
        if not nat_test_passed:
            self.log_message("首次NAT开放性测试失败。将在5秒后重试一次。", is_warning=True)
            time.sleep(5)
            self.log_message("正在重试NAT开放性测试...")
            nat_test_passed = self.network_manager.check_nat_openness_for_unsolicited_responses()
        
        self.can_reliably_receive_calls = nat_test_passed
        self.log_message(f"后台NAT测试完成，最终结果: {self.can_reliably_receive_calls}")

        if self.master.winfo_exists():
            self.master.after(0, lambda: self.ui_handler.update_ui_elements_for_state(
                self.state_manager.app_state, "NAT test completed", None, None
            ))

    def on_closing(self):
        if self._is_closing: return
        self._is_closing = True
        self.log_message("正在关闭应用程序...")
        self.is_running_main_op = False
        
        self.state_manager.handle_app_closing()
        
        if self.master.winfo_exists(): self.master.withdraw()
        if hasattr(self.ui_manager, 'unload_custom_font'): self.ui_manager.unload_custom_font()
        
        threading.Thread(target=self._perform_background_cleanup, daemon=True).start()

    def _perform_background_cleanup(self):
        self.state_manager.cleanup_for_closing()
        self.network_manager.stop_listening()
        self.audio_manager.terminate()
        self.indicator_blinker_timer.stop_thread()
        self.log_message("后台清理完成。销毁主窗口。")
        if self.master.winfo_exists(): self.master.after(0, self.master.destroy)

    def _handle_audio_deduplication(self):
        if not (hasattr(self.master, 'winfo_exists') and self.master.winfo_exists()):
            return

        if self.state_manager.app_state == AppState.IN_CALL:
            self.ui_manager.update_packet_indicator(PACKET_INDICATOR_GREEN_ACK)
            duration_seconds = (PYAUDIO_CHUNK / PYAUDIO_RATE * 2) 
            self.indicator_blinker_timer.set(
                duration_seconds,
                self._revert_indicator_after_deduplication_display
            )

    def _revert_indicator_after_deduplication_display(self):
        if self.master.winfo_exists():
            if self.state_manager.app_state == AppState.IN_CALL:
                self.ui_manager.update_packet_indicator(PACKET_INDICATOR_RED_SENT)
            else: 
                self.ui_manager.update_packet_indicator(PACKET_INDICATOR_IDLE)

    def on_toggle_dev_mode(self):
        self.dev_mode_enabled = not self.dev_mode_enabled
        self.ui_manager.update_dev_mode_visibility(self.dev_mode_enabled)
        self.log_message(f"开发者模式已 {'启用' if self.dev_mode_enabled else '禁用'}")
        self.ui_handler.update_ui_elements_for_state(self.state_manager.app_state, "dev mode toggled", None, None)

    def on_peer_info_changed(self):
        self.ui_handler.update_ui_elements_for_state(self.state_manager.app_state, "peer info changed", None, None)
    
    def generate_and_update_feature_code(self):
        result = self.feature_code_manager.generate_feature_code(self.network_manager.public_ip, self.network_manager.public_port)
        
        if isinstance(result, tuple) and len(result) == 2:
            code, err_msg = result
        else:
            code, err_msg = None, "内部错误：生成格式不正确"
            self.log_message(f"generate_feature_code returned an unexpected value: {result}", "Controller", is_error=True)
            
        self.feature_code_str = err_msg or code or "N/A (生成失败)"
        self.ui_manager.set_feature_code_display(self.feature_code_str)

    def on_copy_feature_code(self):
        if self.feature_code_str and "N/A" not in self.feature_code_str and "错误" not in self.feature_code_str:
            if self.ui_manager.set_clipboard_data(self.feature_code_str):
                self.ui_manager.show_message("已复制", "特征码已复制到剪贴板。", type="info")
        else:
            self.ui_manager.show_message("无特征码", "当前无有效特征码可复制。", type="info")

    def on_paste_feature_code(self):
        code = self.ui_manager.get_clipboard_data()
        if not code:
            self.ui_manager.show_message("信息", "剪贴板为空，请先复制特征码。", type="info")
            return
            
        ip, port, err_msg = self.feature_code_manager.parse_feature_code(code)
        if err_msg:
            self.ui_manager.show_message("解析失败", f"特征码{err_msg}\n请确保特征码正确无误。", type="error")
        else:
            self.ui_manager.set_peer_ip_entry(ip)
            self.ui_manager.set_peer_port_entry(str(port))
            self.ui_manager.show_message("解析成功", f"特征码已解析:\nIP: {ip}\n端口: {port}", type="info")
            
        self.on_peer_info_changed()

if __name__ == "__main__":
    try:
        locale.setlocale(locale.LC_ALL, '') 
    except locale.Error as e:
        print(f"Warning: Could not set system default locale: {e}.")

    root = ctk.CTk()
    icon_path = resource_path(APP_ICON_FILENAME)
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)
    else:
        print(f"Warning: Icon file not found at {icon_path}")
        
    app = AppController(root)
    root.mainloop()