import customtkinter as ctk
import threading
import time
import datetime
import os
import traceback
import winsound
import struct
import socket
import locale

from config import *
from models import AppState, SignalType
from utils import SingleThreadPreciseTimer, FeatureCodeManager, resource_path
from audio_manager import AudioManager
from network_manager import NetworkManager
from ui_manager import UIManager

print("Starting up")
print("Imports done")

class VoiceChatApp:
    def __init__(self, master_tk_root):
        self.master = master_tk_root
        self.app_state = AppState.STARTING
        self._is_closing = False

        self.feature_code_manager = FeatureCodeManager(FEATURE_CODE_KEY)
        self.dev_mode_enabled = False

        self.peer_wants_to_receive_audio = True
        self.my_speaker_switch_is_on = True

        self.ui_manager = UIManager(
            master_tk_root,
            app_callbacks=self._get_ui_callbacks(),
            log_callback=lambda msg, is_error=False, is_warning=False: self.log_message(msg, source="UIManager"),
            app_instance=self
        )

        self.audio_manager = AudioManager(
            log_callback=lambda msg, is_error=False, is_warning=False: self.log_message(msg, source="AudioManager", is_error=is_error, is_warning=is_warning),
            deduplication_callback=self._handle_audio_deduplication
        )
        self.network_manager = NetworkManager(
            log_callback=lambda msg, is_error=False, is_warning=False: self.log_message(msg, source="NetworkManager", is_error=is_error, is_warning=is_warning),
            data_received_callback=self._on_network_data_received
        )

        self.feature_code_str = "N/A (正在初始化...)"
        self.can_reliably_receive_calls = None

        self.peer_full_address = None
        self.peer_address_for_call_attempt = None

        self.is_running_main_op = False
        self.send_thread = None
        self.send_sequence_number = 0

        self.indicator_blinker_timer = SingleThreadPreciseTimer(self.master, name="IndicatorBlinkerThread")
        self.call_request_ack_timer_id = None
        self.hangup_ack_timer_id = None
        self.final_idle_status_timer_id = None
        self.initialization_thread = None

        self.current_hangup_target_address = None
        self.pending_call_rejection_ack_address = None
        self.hangup_retry_count = 0

        self._ui_state_handlers = {
            AppState.STARTING: self._update_ui_for_starting_state,
            AppState.INITIALIZING_NETWORK: self._update_ui_for_initializing_network_state,
            AppState.GETTING_PUBLIC_IP_FAILED: self._update_ui_for_getting_public_ip_failed_state,
            AppState.IDLE: self._update_ui_for_idle_state,
            AppState.CALL_INITIATING_REQUEST: self._update_ui_for_call_initiating_request_state,
            AppState.CALL_OUTGOING_WAITING_ACCEPTANCE: self._update_ui_for_call_outgoing_waiting_acceptance_state,
            AppState.CALL_INCOMING_RINGING: self._update_ui_for_call_incoming_ringing_state,
            AppState.IN_CALL: self._update_ui_for_in_call_state,

            AppState.CALL_TERMINATING_SELF_INITIATED: self._update_ui_for_call_terminating_self_initiated_state,
            AppState.CALL_REJECTING: self._update_ui_for_call_rejecting_state,

            AppState.CALL_ENDED_LOCALLY_HUNG_UP: self._update_ui_for_call_ended_state,
            AppState.CALL_ENDED_PEER_HUNG_UP: self._update_ui_for_call_ended_state,
            AppState.CALL_ENDED_PEER_REJECTED: self._update_ui_for_call_ended_state,
            AppState.CALL_ENDED_ERROR: self._update_ui_for_call_ended_state,
            AppState.CALL_ENDED_REQUEST_FAILED: self._update_ui_for_call_ended_state,
            AppState.CALL_ENDED_APP_CLOSING: self._update_ui_for_call_ended_app_closing_state,
        }

        self._signal_handlers = {
            SignalType.ACK_HANGUP_SIGNAL.value: self._handle_ack_hangup_signal,
            SignalType.ACK_CALL_REQUEST_SIGNAL.value: self._handle_ack_call_request_signal,
            SignalType.CALL_ACCEPTED_SIGNAL.value: self._handle_call_accepted_signal,
            SignalType.HANGUP_SIGNAL.value: self._handle_hangup_signal,
        }

        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.ui_manager.update_status_label("应用界面加载完成，准备初始化...", COLOR_STATUS_INFO)
        self._start_full_initialization_threaded()

    def _start_full_initialization_threaded(self):
        if self.initialization_thread and self.initialization_thread.is_alive():
            self.log_message("初始化线程已在运行。", is_warning=True)
            return

        self.master.after(10, lambda: self._set_app_state(AppState.INITIALIZING_NETWORK, "正在后台初始化网络和服务..."))

        self.initialization_thread = threading.Thread(
            target=self._perform_full_initialization_flow,
            daemon=True,
            name="AppInitializationThread"
        )
        self.initialization_thread.start()

    def _perform_full_audio_initialization_task(self, results):
        self.log_message("音频初始化线程：启动...")

        is_core_success = self.audio_manager.initialize_pyaudio_core()
        results['audio_init_success'] = is_core_success
        
        if not is_core_success:
            self.log_message("音频初始化线程：PyAudio核心初始化失败，终止后续音频任务。", is_error=True)
            return

        self.log_message("音频初始化线程：尝试打开音频输出流...")
        if not self.audio_manager.open_output_stream():
            self.log_message("音频初始化线程：警告: 无法初始化默认音频输出设备。可能无法播放音频。", is_warning=True)
        else:
            self.log_message("音频初始化线程：音频输出流已成功打开。")
            
        self.log_message("音频初始化线程：完成。")

    def _perform_full_network_initialization_task(self, results):
        self.log_message("网络初始化线程：启动...")
        success, message = self.network_manager.start_listening_and_stun()
        results['network_init_success'] = success
        results['network_init_message'] = message

        if self.master.winfo_exists():
            self.master.after(0, self._generate_and_update_feature_code)
        if not success:
            self.log_message("网络初始化线程：启动监听和STUN失败，终止后续网络任务。", is_error=True)
            return

        self.log_message("网络初始化线程：开始NAT开放性测试...")
        nat_test_passed = self.network_manager.check_nat_openness_for_unsolicited_responses()
        if not nat_test_passed:
            self.log_message("网络初始化线程：首次NAT开放性测试失败。将在5秒后重试一次。", is_warning=True)
            time.sleep(5)
            self.log_message("网络初始化线程：正在重试NAT开放性测试...")
            nat_test_passed = self.network_manager.check_nat_openness_for_unsolicited_responses()

        self.can_reliably_receive_calls = nat_test_passed
        self.log_message(f"网络初始化线程：NAT开放性测试完成，最终结果: {self.can_reliably_receive_calls}")

        if self.master.winfo_exists():
            self.master.after(0, self._update_ui_elements_for_state, "NAT检测完成")
        self.log_message("网络初始化线程：完成。")

    def _perform_full_initialization_flow(self):
        self.log_message("后台初始化流程已启动")

        if self.is_running_main_op:
            self.log_message("后台初始化：服务已在运行中 (不应发生)。", is_warning=True)
            self.master.after(0, self._update_ui_elements_for_state)
            return

        results = {}

        audio_thread = threading.Thread(
            target=self._perform_full_audio_initialization_task,
            args=(results,),
            daemon=True,
            name="FullAudioInitThread"
        )
        network_thread = threading.Thread(
            target=self._perform_full_network_initialization_task,
            args=(results,),
            daemon=True,
            name="FullNetworkInitThread"
        )

        self.log_message("正在启动音频和网络初始化...")
        audio_thread.start()
        network_thread.start()

        audio_thread.join()
        network_thread.join()
        self.log_message("所有并行初始化任务已完成。开始检查结果...")

        if not results.get('audio_init_success', False):
            self.master.after(0, self._set_app_state, AppState.CALL_ENDED_ERROR, "PyAudio核心初始化失败，应用无法使用。")
            self.master.after(0, lambda: self.ui_manager.show_message("严重错误", "PyAudio核心初始化失败。\n请检查音频设备和驱动程序。", type="error"))
            self.is_running_main_op = False
            return

        if not results.get('network_init_success', False):
            network_fail_message = results.get('network_init_message', "网络服务启动失败")
            self.master.after(0, self._set_app_state, AppState.GETTING_PUBLIC_IP_FAILED, network_fail_message)
            self.is_running_main_op = False
            return

        self.is_running_main_op = True
        
        if self.network_manager.public_ip and self.network_manager.public_port:
            self.master.after(0, self._set_app_state, AppState.IDLE, "初始化完成，应用已就绪。")
        else:
            reason_for_fail = results.get('network_init_message', "公网地址获取失败")
            self.master.after(0, self._set_app_state, AppState.GETTING_PUBLIC_IP_FAILED, f"{reason_for_fail} 应用已就绪。")

        self.log_message("所有后台初始化任务已全部完成。应用已就绪。")

    def _get_ui_callbacks(self):
        return {
            "ui_on_call_hangup_button_clicked": self._ui_on_call_hangup_button_clicked,
            "ui_on_paste_feature_code": self._ui_on_paste_feature_code,
            "ui_on_copy_feature_code": self._ui_on_copy_feature_code,
            "ui_on_toggle_mic": self._ui_on_toggle_mic,
            "ui_on_toggle_speaker": self._ui_on_toggle_speaker,
            "ui_on_toggle_dev_mode": self._ui_on_toggle_dev_mode,
            "ui_on_peer_info_changed": self._ui_on_peer_info_changed,
            "ui_force_peer_field_update": self._update_ui_elements_for_state,
            "ui_on_accept_call": self._ui_on_accept_call_clicked,
            "ui_on_reject_call": self._ui_on_reject_call_clicked,
        }

    def log_message(self, message, source="App", is_error=False, is_warning=False):
        now = datetime.datetime.now()
        formatted_time = now.strftime('%H:%M:%S') + f".{now.microsecond // 1000:03d}"
        state_name = self.app_state.name if hasattr(self, 'app_state') and self.app_state else "UNSET_STATE"

        log_level = "INFO"
        if is_error: log_level = "ERROR"
        elif is_warning: log_level = "WARN"

        log_entry = f"{formatted_time} [{state_name}] [{source}] [{log_level}] - {message}"

        print(log_entry)
        if hasattr(self, 'ui_manager'):
            self.ui_manager.log_to_ui_textbox(log_entry, self.dev_mode_enabled)

    def _set_app_state(self, new_state: AppState, reason="", peer_address_tuple=None, associated_data=None):
        old_state = self.app_state
        self.app_state = new_state
        self.log_message(f"状态从 {old_state.name} 变为 {new_state.name}. 原因: '{reason}' "
                         f"对方: {peer_address_tuple if peer_address_tuple else 'N/A'} "
                         f"数据: {associated_data if associated_data else 'N/A'}")

        if self.master.winfo_exists():
            self.master.after(0, self._update_ui_elements_for_state, reason, peer_address_tuple, associated_data)
        elif self.app_state != AppState.CALL_ENDED_APP_CLOSING:
             self.log_message(f"Master window does not exist, UI not updated for state {new_state.name}", is_warning=True)

    def _get_peer_display_name_for_ui(self, current_peer_address_tuple=None):
        temp_peer_addr_for_display = current_peer_address_tuple

        if not temp_peer_addr_for_display:
            if self.app_state in [
                AppState.CALL_INITIATING_REQUEST, AppState.CALL_OUTGOING_WAITING_ACCEPTANCE, AppState.IN_CALL,
                AppState.CALL_INCOMING_RINGING, AppState.CALL_TERMINATING_SELF_INITIATED, AppState.CALL_REJECTING
            ]:
                if self.peer_full_address:
                    temp_peer_addr_for_display = self.peer_full_address
                elif self.peer_address_for_call_attempt: 
                    temp_peer_addr_for_display = self.peer_address_for_call_attempt
                elif self.current_hangup_target_address: 
                    temp_peer_addr_for_display = self.current_hangup_target_address
        
        if temp_peer_addr_for_display:
            return f"{temp_peer_addr_for_display[0]}:{temp_peer_addr_for_display[1]}"
        elif hasattr(self.ui_manager, 'ent_peer_ip'): 
            _ip = self.ui_manager.get_peer_ip_entry()
            _port = self.ui_manager.get_peer_port_entry()
            if _ip and _port:
                return f"{_ip}:{_port}"
        return "对方" 

    def _update_ui_for_call_terminating_self_initiated_state(self, peer_address_tuple):
        peer_display_name = self._get_peer_display_name_for_ui(peer_address_tuple)
        status_msg = f"{STATUS_LOCALLY_HUNG_UP} ({peer_display_name})"
        
        can_call_again = self._is_peer_info_valid(self.ui_manager.get_peer_ip_entry(), self.ui_manager.get_peer_port_entry()) and \
                         self.audio_manager.is_initialized() and self.is_running_main_op

        return {
            "status_message": status_msg,
            "status_color": COLOR_STATUS_SUCCESS,
            "call_btn_text": "呼叫",
            "call_btn_fg_color": self.ui_manager.default_button_color,
            "call_btn_hover_color": self.ui_manager.default_button_hover_color,
            "call_btn_text_color": self.ui_manager.default_button_text_color,
            "call_btn_state": "normal" if can_call_again else "disabled",
            "peer_entry_enabled": True, "parse_btn_enabled": True,
        }
    
    def _update_ui_for_call_rejecting_state(self, peer_address_tuple):
        peer_display_name = self._get_peer_display_name_for_ui(peer_address_tuple)
        status_msg = f"已拒绝来自 {peer_display_name} 的呼叫"
        
        can_call_again = self._is_peer_info_valid(self.ui_manager.get_peer_ip_entry(), self.ui_manager.get_peer_port_entry()) and \
                         self.audio_manager.is_initialized() and self.is_running_main_op
        return {
            "status_message": status_msg,
            "status_color": COLOR_STATUS_WARNING,
            "call_btn_text": "呼叫",
            "call_btn_fg_color": self.ui_manager.default_button_color,
            "call_btn_hover_color": self.ui_manager.default_button_hover_color,
            "call_btn_text_color": self.ui_manager.default_button_text_color,
            "call_btn_state": "normal" if can_call_again else "disabled",
            "peer_entry_enabled": True, "parse_btn_enabled": True,
        }

    def _update_ui_for_starting_state(self):
        return {
            "status_message": "正在启动...",
            "status_color": COLOR_STATUS_INFO,
            "call_btn_state": "disabled",
            "local_ip_text": "启动中...", "local_port_text": "启动中...",
            "feature_code_text": "N/A (启动中...)"
        }
    
    def _update_ui_for_initializing_network_state(self, reason, peer_address_tuple, associated_data):
        return {
            "status_message": reason if reason else "正在初始化网络...",
            "status_color": COLOR_STATUS_INFO,
            "call_btn_state": "disabled",
            "local_ip_text": "获取中...", "local_port_text": "获取中...",
            "feature_code_text": "等待公网地址"
        }

    def _update_ui_for_getting_public_ip_failed_state(self, reason, peer_address_tuple, associated_data):
        _reason = reason if reason else "公网地址获取失败"
        status_message = _reason
        call_btn_state = "disabled"

        if self.audio_manager.is_initialized():
            _ip = self.ui_manager.get_peer_ip_entry()
            _port = self.ui_manager.get_peer_port_entry()
            if self._is_peer_info_valid(_ip, _port):
                call_btn_state = "normal"
                status_message = f"公网IP获取失败, 但仍可尝试呼叫/接收。"
            else:
                status_message = f"公网IP获取失败, 且无远端信息。"
        else:
            status_message = "PyAudio错误,无法启动"
            call_btn_state = "disabled"
        
        if self.audio_manager.is_initialized() and self.network_manager.local_port:
            status_message = STATUS_WAITING_FOR_REMOTE_INFO

        self._generate_and_update_feature_code()
        return {
            "status_message": status_message,
            "status_color": COLOR_STATUS_ERROR,
            "peer_entry_enabled": True, "parse_btn_enabled": True,
            "call_btn_state": call_btn_state,
            "local_ip_text": self.network_manager.public_ip or "获取失败",
            "local_port_text": str(self.network_manager.public_port or "N/A")
        }

    def _update_ui_for_idle_state(self, reason, peer_address_tuple, associated_data):
        status_message = STATUS_WAITING_FOR_REMOTE_INFO
        status_color = COLOR_STATUS_INFO
        call_btn_state = "disabled"

        _ip = self.ui_manager.get_peer_ip_entry()
        _port = self.ui_manager.get_peer_port_entry()
        if self._is_peer_info_valid(_ip, _port):
            status_message = STATUS_READY_TO_CALL_OR_RECEIVE
            if self.audio_manager.is_initialized() and self.is_running_main_op:
                call_btn_state = "normal"
        
        self._generate_and_update_feature_code()
        return {
            "status_message": status_message, "status_color": status_color,
            "peer_entry_enabled": True, "parse_btn_enabled": True,
            "call_btn_state": call_btn_state,
            "local_ip_text": self.network_manager.public_ip or "N/A (STUN失败)",
            "local_port_text": str(self.network_manager.public_port or "N/A")
        }

    def _update_ui_for_call_active_states_base(self, reason, peer_address_tuple, associated_data, status_message_template, status_color, packet_indicator_color=None):
        peer_display_name = self._get_peer_display_name_for_ui(peer_address_tuple)
        return {
            "call_btn_text": "挂断",
            "call_btn_fg_color": COLOR_BUTTON_REJECT_BG,
            "call_btn_hover_color": COLOR_BUTTON_REJECT_HOVER_BG,
            "call_btn_text_color": COLOR_BUTTON_CALL_FG,
            "call_btn_state": "normal",
            "peer_entry_enabled": False, "parse_btn_enabled": False,
            "status_message": status_message_template.format(peer_display_name=peer_display_name),
            "status_color": status_color,
            "packet_indicator_color_override": packet_indicator_color
        }
    
    def _update_ui_for_call_initiating_request_state(self, reason, peer_address_tuple, associated_data):
        return self._update_ui_for_call_active_states_base(
            reason, peer_address_tuple, associated_data,
            f"{STATUS_SENDING_CALL_REQUEST} ({{peer_display_name}})",
            COLOR_STATUS_CALLING
        )

    def _update_ui_for_call_outgoing_waiting_acceptance_state(self, reason, peer_address_tuple, associated_data):
        return self._update_ui_for_call_active_states_base(
            reason, peer_address_tuple, associated_data,
            "正在呼叫 {peer_display_name}... (等待对方接听)",
            COLOR_STATUS_CALLING
        )

    def _update_ui_for_in_call_state(self, reason, peer_address_tuple, associated_data):
        return self._update_ui_for_call_active_states_base(
            reason, peer_address_tuple, associated_data,
            "通话中 - {peer_display_name}",
            COLOR_STATUS_SUCCESS,
            PACKET_INDICATOR_RED_SENT 
        )

    def _update_ui_for_call_incoming_ringing_state(self, reason, peer_address_tuple, associated_data):
        peer_display_name = self._get_peer_display_name_for_ui(peer_address_tuple)
        return {
            "status_message": reason if reason else f"收到来自 {peer_display_name} 的呼叫",
            "status_color": COLOR_STATUS_INFO,
            "peer_entry_enabled": False, "parse_btn_enabled": False,
        }
        
    def _update_ui_for_call_ended_state(self, reason, peer_address_tuple, associated_data):
        status_message = reason if reason else "通话已结束"
        status_color = COLOR_STATUS_DEFAULT
        call_btn_state = "disabled"

        if self.app_state == AppState.CALL_ENDED_LOCALLY_HUNG_UP:
            status_color = COLOR_STATUS_SUCCESS
            if not reason and peer_address_tuple:
                 status_message = f"{STATUS_LOCALLY_HUNG_UP} ({self._get_peer_display_name_for_ui(peer_address_tuple)})"
            elif not reason:
                 status_message = STATUS_LOCALLY_HUNG_UP
        elif self.app_state == AppState.CALL_ENDED_PEER_HUNG_UP:
            status_color = COLOR_STATUS_WARNING
        elif self.app_state == AppState.CALL_ENDED_PEER_REJECTED:
            status_color = COLOR_STATUS_WARNING
            if not reason and peer_address_tuple:
                status_message = f"已拒绝来自 {self._get_peer_display_name_for_ui(peer_address_tuple)} 的呼叫"
            elif not reason:
                status_message = "呼叫被拒绝"
        elif self.app_state == AppState.CALL_ENDED_ERROR or self.app_state == AppState.CALL_ENDED_REQUEST_FAILED:
            status_color = COLOR_STATUS_ERROR

        _ip = self.ui_manager.get_peer_ip_entry()
        _port = self.ui_manager.get_peer_port_entry()
        if self.audio_manager.is_initialized() and self._is_peer_info_valid(_ip, _port) and self.is_running_main_op:
            call_btn_state = "normal"

        if self.app_state != AppState.CALL_ENDED_APP_CLOSING:
            if self.final_idle_status_timer_id is not None:
                self.master.after_cancel(self.final_idle_status_timer_id)
                self.final_idle_status_timer_id = None 
            
            self.log_message(f"在 {self.app_state.name} 状态后，安排{CALL_END_UI_RESET_DELAY_MS / 1000}秒后检查是否转换到IDLE状态。")
            self.final_idle_status_timer_id = self.master.after(
                CALL_END_UI_RESET_DELAY_MS, 
                self._finalize_ui_after_hangup_delay
            )
        return {
            "peer_entry_enabled": True, "parse_btn_enabled": True,
            "status_message": status_message, "status_color": status_color,
            "call_btn_state": call_btn_state,
        }

    def _update_ui_for_call_ended_app_closing_state(self, reason, peer_address_tuple, associated_data):
        if self.final_idle_status_timer_id is not None: 
            self.master.after_cancel(self.final_idle_status_timer_id)
            self.final_idle_status_timer_id = None
        return {
            "status_message": "程序正在关闭...",
            "status_color": COLOR_STATUS_INFO,
            "call_btn_state": "disabled",
            "peer_entry_enabled": False, "parse_btn_enabled": False,
        }
        
    def _update_ui_for_unknown_state(self, reason, peer_address_tuple, associated_data):
        self.log_message(f"警告: 未知的UI状态处理: {self.app_state.name}", is_warning=True)
        return {
            "status_message": "状态未知",
            "status_color": COLOR_STATUS_DEFAULT,
            "call_btn_state": "disabled"
        }

    def _update_ui_elements_for_state(self, reason="", peer_address_tuple=None, associated_data=None):
        if not (hasattr(self, 'ui_manager') and self.master.winfo_exists()) and self.app_state != AppState.CALL_ENDED_APP_CLOSING:
            self.log_message("UI Manager or master window not available for UI update.", is_warning=True)
            return

        ui_config = {
            "call_btn_text": "呼叫",
            "call_btn_command": self._ui_on_call_hangup_button_clicked,
            "call_btn_fg_color": self.ui_manager.default_button_color,
            "call_btn_hover_color": self.ui_manager.default_button_hover_color,
            "call_btn_text_color": self.ui_manager.default_button_text_color,
            "call_btn_state": "disabled",
            "peer_entry_enabled": False,
            "parse_btn_enabled": False,
            "status_message": "状态未知",
            "status_color": COLOR_STATUS_DEFAULT,
            "packet_indicator_color_override": None,
            "local_ip_text": None, 
            "local_port_text": None,
            "feature_code_text": None
        }

        handler = self._ui_state_handlers.get(self.app_state, self._update_ui_for_unknown_state)
        state_specific_config = handler(reason, peer_address_tuple, associated_data)
        ui_config.update(state_specific_config)

        if ui_config["local_ip_text"] is not None and ui_config["local_port_text"] is not None:
            self.ui_manager.set_local_ip_port_display(ui_config["local_ip_text"], ui_config["local_port_text"])
        if ui_config["feature_code_text"] is not None:
            self.ui_manager.set_feature_code_display(ui_config["feature_code_text"])

        self.ui_manager.update_status_label(ui_config["status_message"], ui_config["status_color"])

        if self.app_state == AppState.CALL_INCOMING_RINGING:
            self.ui_manager.set_call_button_mode("accept_reject")
            self.ui_manager.configure_call_button( 
                text="振铃中...", command=None,
                fg_color=self.ui_manager.default_button_color,
                hover_color=self.ui_manager.default_button_hover_color,
                text_color=self.ui_manager.default_button_text_color,
                state="disabled"
            )
        else:
            self.ui_manager.set_call_button_mode("single")
            self.ui_manager.configure_call_button(
                ui_config["call_btn_text"], ui_config["call_btn_command"],
                ui_config["call_btn_fg_color"], ui_config["call_btn_hover_color"],
                ui_config["call_btn_text_color"], ui_config["call_btn_state"]
            )

        can_edit_peer_fields = (self.dev_mode_enabled or not self.feature_code_str or "N/A" in self.feature_code_str or "错误" in self.feature_code_str) and ui_config["peer_entry_enabled"]
        final_peer_entry_state = "normal" if can_edit_peer_fields else "disabled"
        final_parse_btn_state = "normal" if ui_config["parse_btn_enabled"] else "disabled"

        self.ui_manager.configure_peer_input_fields(
            final_peer_entry_state, final_peer_entry_state, final_parse_btn_state
        )

        is_blinker_currently_active = False
        if hasattr(self, 'indicator_blinker_timer'): 
            is_blinker_currently_active = self.indicator_blinker_timer.is_active()

        if self.app_state != AppState.IN_CALL and is_blinker_currently_active:
            self.indicator_blinker_timer.cancel()
            is_blinker_currently_active = False 

        if not is_blinker_currently_active:
            if ui_config["packet_indicator_color_override"] is not None:
                self.ui_manager.update_packet_indicator(ui_config["packet_indicator_color_override"])
            elif self.app_state == AppState.IN_CALL:
                self.ui_manager.update_packet_indicator(PACKET_INDICATOR_RED_SENT)
            else: 
                self.ui_manager.update_packet_indicator(PACKET_INDICATOR_IDLE)

        self.ui_manager.update_mute_switch_text(self.audio_manager.mic_muted, not self.my_speaker_switch_is_on)

    def _is_peer_info_valid(self, ip_str, port_str):
        if not ip_str or not port_str: return False
        try:
            socket.inet_aton(ip_str)
            port_int = int(port_str)
            return 1 <= port_int <= 65535
        except (ValueError, socket.error):
            return False

    def _generate_and_update_feature_code(self):
        code, err_msg = self.feature_code_manager.generate_feature_code(
            self.network_manager.public_ip, self.network_manager.public_port
        )
        if err_msg:
            self.feature_code_str = err_msg
        else:
            self.feature_code_str = code

        if hasattr(self, 'ui_manager'):
            self.ui_manager.set_feature_code_display(self.feature_code_str)

    def _ui_on_call_hangup_button_clicked(self):
        current_action_state = self.app_state

        if current_action_state in [
            AppState.CALL_INITIATING_REQUEST, AppState.CALL_OUTGOING_WAITING_ACCEPTANCE,
            AppState.IN_CALL
        ]:
            self.handle_local_hangup_action()
        elif current_action_state in [
            AppState.IDLE, AppState.GETTING_PUBLIC_IP_FAILED,
            AppState.CALL_ENDED_LOCALLY_HUNG_UP, AppState.CALL_ENDED_PEER_HUNG_UP,
            AppState.CALL_ENDED_PEER_REJECTED, AppState.CALL_ENDED_ERROR,
            AppState.CALL_ENDED_REQUEST_FAILED
        ]:
            if self.current_hangup_target_address is not None:
                self.log_message(f"用户尝试新呼叫，取消对 {self.current_hangup_target_address} 的先前挂断/拒绝后台静默重试。")
                if self.hangup_ack_timer_id is not None:
                    self.master.after_cancel(self.hangup_ack_timer_id)
                    self.hangup_ack_timer_id = None
                self.current_hangup_target_address = None
                self.pending_call_rejection_ack_address = None
                self.hangup_retry_count = 0
            
            self.master.after(50, self._initiate_call_sequence)
        else:
            self.log_message(f"呼叫/挂断按钮按下，但应用状态 ({current_action_state.name}) 不支持操作。")

    def _ui_on_paste_feature_code(self):
        code_from_clipboard = self.ui_manager.get_clipboard_data()
        if not code_from_clipboard:
            self.ui_manager.show_message("信息", "剪贴板为空，请先复制特征码。", type="info")
            return

        ip, port, err_msg = self.feature_code_manager.parse_feature_code(code_from_clipboard)
        if err_msg:
            self.log_message(f"解析特征码错误: {err_msg} (原始码: '{code_from_clipboard[:30]}...')")
            self.ui_manager.show_message("解析失败", f"特征码{err_msg}\n请确保特征码正确无误。", type="error")
        else:
            self.ui_manager.set_peer_ip_entry(ip)
            self.ui_manager.set_peer_port_entry(str(port))
            self.log_message(f"特征码成功解析: IP={ip}, Port={port} (来自剪贴板)")
            self.ui_manager.show_message("解析成功", f"特征码已解析:\nIP: {ip}\n端口: {port}", type="info")
        self._update_ui_elements_for_state() 

    def _ui_on_copy_feature_code(self):
        if self.feature_code_str and "N/A" not in self.feature_code_str and "错误" not in self.feature_code_str:
            if self.ui_manager.set_clipboard_data(self.feature_code_str):
                self.log_message(f"本机特征码 '{self.feature_code_str}' 已复制到剪贴板。")
                self.ui_manager.show_message("已复制", "特征码已复制到剪贴板。", type="info")
            else:
                self.log_message(f"复制特征码失败 (UI)", is_error=True)
                self.ui_manager.show_message("复制失败", "无法复制到剪贴板。", type="warning")
        else:
            self.ui_manager.show_message("无特征码", "当前无有效特征码可复制。", type="info")

    def _ui_on_toggle_mic(self):
        mic_muted = self.audio_manager.toggle_mic_mute()
        self.ui_manager.update_mute_switch_text(mic_muted, not self.my_speaker_switch_is_on)

    def _ui_on_toggle_speaker(self):
        self.my_speaker_switch_is_on = not self.my_speaker_switch_is_on
        self.ui_manager.update_mute_switch_text(self.audio_manager.mic_muted, not self.my_speaker_switch_is_on)

        self.log_message(f"本机扬声器开关已切换为: {'开启' if self.my_speaker_switch_is_on else '关闭'}")
        if self.app_state == AppState.IN_CALL and self.peer_full_address:
            status_payload = b"ON" if self.my_speaker_switch_is_on else b"OFF"
            signal = SignalType.SPEAKER_STATUS_SIGNAL_PREFIX.value + status_payload
            if self.network_manager.send_packet(signal, self.peer_full_address):
                self.log_message(f"已将本机扬声器开关状态 ({status_payload.decode()}) 发送给 {self.peer_full_address}")
            else:
                self.log_message(f"发送本机扬声器开关状态至 {self.peer_full_address} 失败", is_warning=True)

    def _ui_on_toggle_dev_mode(self):
        self.dev_mode_enabled = not self.dev_mode_enabled
        self.ui_manager.update_dev_mode_visibility(self.dev_mode_enabled)
        self.log_message(f"开发者模式已 {'启用' if self.dev_mode_enabled else '禁用'}")
        self._update_ui_elements_for_state()

    def _ui_on_peer_info_changed(self):
        if self.app_state in [AppState.IDLE, AppState.GETTING_PUBLIC_IP_FAILED] or \
           self.app_state.name.startswith("CALL_ENDED_"):
            self._update_ui_elements_for_state()

    def _ui_on_accept_call_clicked(self):
        if self.app_state == AppState.CALL_INCOMING_RINGING:
            if not self.peer_full_address: 
                self.log_message("CRITICAL: 尝试接听但 peer_full_address 未设置。", is_error=True)
                self.handle_call_error("内部错误 (接听时无对方地址)", None)
                return

            self.log_message(f"用户接听了来自 {self.peer_full_address} 的呼叫。")
            self._proceed_with_call_setup(is_accepting_call=True)
        else:
            self.log_message(f"接听按钮按下，但应用状态 ({self.app_state.name}) 不正确。忽略。", is_warning=True)

    def _ui_on_reject_call_clicked(self):
        if self.app_state == AppState.CALL_INCOMING_RINGING:
            if not self.peer_full_address:
                self.log_message("CRITICAL: 尝试拒绝但 peer_full_address 未设置。", is_error=True)
                self.handle_call_error("内部错误 (拒绝时无对方地址)", None)
                return
            
            self.log_message(f"用户拒绝了来自 {self.peer_full_address} 的呼叫。")
            self.handle_local_hangup_action()
        else:
            self.log_message(f"拒绝按钮按下，但应用状态 ({self.app_state.name}) 不正确。忽略。", is_warning=True)

    def _initiate_call_sequence(self):
        if not self.audio_manager.is_initialized():
            self.ui_manager.show_message("错误", "PyAudio 未初始化，无法呼叫。", type="error")
            self._set_app_state(AppState.GETTING_PUBLIC_IP_FAILED, reason="PyAudio错误，无法呼叫。") 
            return

        if not self.is_running_main_op: 
            self.ui_manager.show_message("未就绪", "网络服务未成功启动或未在监听状态。", type="warning")
            return

        if self.app_state not in [
            AppState.IDLE, AppState.GETTING_PUBLIC_IP_FAILED,
            AppState.CALL_ENDED_LOCALLY_HUNG_UP, AppState.CALL_ENDED_PEER_HUNG_UP,
            AppState.CALL_ENDED_PEER_REJECTED, AppState.CALL_ENDED_ERROR,
            AppState.CALL_ENDED_REQUEST_FAILED
        ]:
            self.log_message(f"不能发起新呼叫，当前状态: {self.app_state.name}")
            self.ui_manager.show_message("提示", "已在通话中或正在尝试呼叫/挂断。\n请等待当前操作完成。", type="info")
            return

        if self.app_state == AppState.GETTING_PUBLIC_IP_FAILED and not (self.network_manager.public_ip and self.network_manager.public_port):
            if not self.ui_manager.show_message("警告", "本机公网地址获取失败。\n呼叫可能仅在局域网内成功，或完全失败。\n是否继续尝试呼叫？", type="askyesno"):
                return
            self.log_message("用户选择在公网地址获取失败的情况下继续呼叫。")

        peer_ip_str = self.ui_manager.get_peer_ip_entry()
        peer_port_str = self.ui_manager.get_peer_port_entry()

        if not self._is_peer_info_valid(peer_ip_str, peer_port_str):
            self.ui_manager.show_message("对方信息无效", "请输入有效的对方 IP 和端口。", type="error")
            return

        self.peer_address_for_call_attempt = (peer_ip_str,int(peer_port_str))

        init_signal = SignalType.CALL_REQUEST_SIGNAL_PREFIX.value

        self._set_app_state(AppState.CALL_INITIATING_REQUEST, 
                            reason=f"向 {self.peer_address_for_call_attempt} 发送呼叫请求",
                            peer_address_tuple=self.peer_address_for_call_attempt)

        if self.call_request_ack_timer_id is not None:
            self.master.after_cancel(self.call_request_ack_timer_id)
            self.call_request_ack_timer_id = None 
        self.call_request_ack_timer_id = self.master.after(
            CALL_REQUEST_ACK_TIMEOUT_MS, 
            self._handle_call_request_ack_timeout
        )

        success = self.network_manager.send_packet(init_signal, self.peer_address_for_call_attempt)
        if success:
            self.log_message(f"向 {self.peer_address_for_call_attempt} 发送呼叫请求。")
        else: 
            self.log_message(f"发送呼叫请求信号失败 (NetworkManager报告失败).")
            if self.call_request_ack_timer_id is not None: 
                self.master.after_cancel(self.call_request_ack_timer_id)
                self.call_request_ack_timer_id = None
            
            self.ui_manager.show_message("呼叫错误", "发送呼叫请求失败 (套接字错误)。", type="error")
            self._transition_to_call_ended_state(
                AppState.CALL_ENDED_REQUEST_FAILED,
                f"呼叫请求发送错误 ({self.peer_address_for_call_attempt[0] if self.peer_address_for_call_attempt else '未知'})",
                self.peer_address_for_call_attempt,
                cleanup_resources=False 
            )

    def _proceed_with_call_setup(self, is_accepting_call=False):
            if not is_accepting_call:
                if self.app_state in [AppState.CALL_OUTGOING_WAITING_ACCEPTANCE, AppState.IN_CALL]:
                    self.log_message(f"_proceed_with_call_setup (outgoing call) called while state is {self.app_state.name}. Potential repeat. Ignoring.", is_warning=True)
                    return
            else:
                if self.app_state == AppState.IN_CALL:
                    self.log_message(f"_proceed_with_call_setup (incoming call) called while already IN_CALL. Potential repeat. Ignoring.", is_warning=True)
                    return

            if not is_accepting_call and self.app_state != AppState.CALL_INITIATING_REQUEST:
                self.log_message(f"_proceed_with_call_setup (outgoing call) called with unexpected state {self.app_state.name}. Proceeding cautiously.", is_warning=True)
            if is_accepting_call and self.app_state != AppState.CALL_INCOMING_RINGING:
                self.log_message(f"_proceed_with_call_setup (incoming call) called with unexpected state {self.app_state.name}. Proceeding cautiously.", is_warning=True)


            if not is_accepting_call: 
                if not self.peer_address_for_call_attempt:
                    self.log_message("CRITICAL: _proceed_with_call_setup (拨出) 但 peer_address_for_call_attempt 为空。", is_error=True)
                    self._transition_to_call_ended_state(AppState.CALL_ENDED_ERROR, "内部呼叫错误 (无尝试地址)")
                    return
                self.peer_full_address = self.peer_address_for_call_attempt
                self.peer_address_for_call_attempt = None 
                self.log_message(f"呼叫请求ACK已收到。目标地址确认为: {self.peer_full_address}")

            if not self.peer_full_address: 
                self.log_message("CRITICAL: _proceed_with_call_setup 但 self.peer_full_address 为空。", is_error=True)
                reason_suffix = "(接听)" if is_accepting_call else "(拨出)"
                self._transition_to_call_ended_state(AppState.CALL_ENDED_ERROR, f"内部呼叫错误 (无对方地址 {reason_suffix})")
                return

            self.peer_wants_to_receive_audio = True
            self.my_speaker_switch_is_on = True

            if hasattr(self, 'ui_manager') and hasattr(self.ui_manager, 'switch_speaker_mute') and self.ui_manager.switch_speaker_mute.winfo_exists():
                current_switch_state_int = self.ui_manager.switch_speaker_mute.get()
                
                if self.my_speaker_switch_is_on and current_switch_state_int == 0:
                    self.ui_manager.switch_speaker_mute.select()
                    self.log_message("同步UI: 扬声器开关已从视觉关闭状态切换为开启状态以匹配内部状态。")
                elif not self.my_speaker_switch_is_on and current_switch_state_int == 1:
                    self.ui_manager.switch_speaker_mute.deselect()
                    self.log_message("同步UI: 扬声器开关已从视觉开启状态切换为关闭状态以匹配内部状态。")

                self.ui_manager.update_mute_switch_text(self.audio_manager.mic_muted, not self.my_speaker_switch_is_on)
            else:
                self.log_message("警告: _proceed_with_call_setup 中无法访问 UI Manager 或扬声器开关。", is_warning=True)


            self.send_sequence_number = 0
            self.audio_manager.clear_played_sequence_numbers()

            if not self.audio_manager.open_input_stream():
                self.handle_call_error("麦克风打开失败", self.peer_full_address)
                return

            if self.send_thread is None or not self.send_thread.is_alive():
                self.send_thread = threading.Thread(target=self._send_audio_loop_target, daemon=True, name="SendAudioThread")
                self.send_thread.start()
            else:
                self.log_message("警告: 发送线程已存在或仍在运行，在 _proceed_with_call_setup 中。", is_warning=True)

            my_speaker_status_payload = b"ON" if self.my_speaker_switch_is_on else b"OFF"
            my_speaker_status_signal = SignalType.SPEAKER_STATUS_SIGNAL_PREFIX.value + my_speaker_status_payload

            if is_accepting_call: # 我方是被叫方，现在接听
                self.network_manager.send_packet(SignalType.CALL_ACCEPTED_SIGNAL.value, self.peer_full_address)
                self.log_message(f"已发送 CALL_ACCEPTED 至 {self.peer_full_address}")

                if self.network_manager.send_packet(my_speaker_status_signal, self.peer_full_address):
                    self.log_message(f"通话建立(接听): 已将本机扬声器开关状态 ({my_speaker_status_payload.decode()}) 发送给 {self.peer_full_address}")
                else:
                    self.log_message(f"通话建立(接听): 发送本机扬声器开关状态至 {self.peer_full_address} 失败", is_warning=True)


                self._play_notification_sound(SOUND_CALL_CONNECTED) 
                self._set_app_state(AppState.IN_CALL, 
                                    reason=f"已接听来自 {self.peer_full_address[0]} 的呼叫",
                                    peer_address_tuple=self.peer_full_address)
            else:
                self._set_app_state(AppState.CALL_OUTGOING_WAITING_ACCEPTANCE,
                                    reason=f"等待 {self.peer_full_address[0]} 接听",
                                    peer_address_tuple=self.peer_full_address)

    def _cleanup_active_call_resources(self):
        self.log_message("清理活动通话资源 (麦克风, 发送线程)...")
        if hasattr(self, 'audio_manager') and self.audio_manager:
            self.audio_manager.close_input_stream() 
            self.audio_manager.clear_played_sequence_numbers() 

        if self.send_thread and self.send_thread.is_alive():
            self.log_message("请求发送线程停止 (通过状态变化)...")
            try: 
                self.send_thread.join(timeout=0.25)
            except Exception as e_j: 
                self.log_message(f"发送线程join出错 (资源清理): {e_j}")
            if self.send_thread and self.send_thread.is_alive(): 
                self.log_message("资源清理: 发送线程join超时。", is_warning=True)
        self.send_thread = None

    def _simple_reset_call_vars_and_set_state(self, reason_for_display, target_state: AppState,
                                           peer_address_tuple=None, *,
                                           cancel_active_hangup_retries=True):
        self.log_message(f"重置呼叫相关变量。目标状态: {target_state.name}, 原因: '{reason_for_display}', "
                         f"取消挂断重试: {cancel_active_hangup_retries}")

        self.peer_full_address = None
        self.peer_address_for_call_attempt = None

        self.peer_wants_to_receive_audio = True
        self.my_speaker_switch_is_on = True

        if cancel_active_hangup_retries:
            if self.hangup_ack_timer_id is not None:
                if self.master.winfo_exists():
                    try:
                        self.master.after_cancel(self.hangup_ack_timer_id)
                    except Exception as e_cancel: # 捕获通用异常以防万一
                        self.log_message(f"取消 hangup_ack_timer 时出错: {e_cancel}", is_warning=True)
                self.hangup_ack_timer_id = None

            if self.current_hangup_target_address or self.pending_call_rejection_ack_address:
                self.log_message(f"取消活动的挂断/拒绝重试。当前目标: {self.current_hangup_target_address}, "
                                 f"拒绝目标: {self.pending_call_rejection_ack_address}")
            self.current_hangup_target_address = None
            self.pending_call_rejection_ack_address = None
            self.hangup_retry_count = 0

        self._set_app_state(target_state, reason=reason_for_display, peer_address_tuple=peer_address_tuple)

    def _determine_hangup_target_address(self, current_app_state: AppState):
        if current_app_state in [
            AppState.IN_CALL, AppState.CALL_OUTGOING_WAITING_ACCEPTANCE, AppState.CALL_INCOMING_RINGING
        ]:
            return self.peer_full_address
        elif current_app_state == AppState.CALL_INITIATING_REQUEST:
            return self.peer_address_for_call_attempt
        elif current_app_state in [AppState.CALL_TERMINATING_SELF_INITIATED, AppState.CALL_REJECTING]:
            return self.current_hangup_target_address
        return None

    def _is_state_active_or_pending_call(self, state: AppState) -> bool:
        return state in [
            AppState.CALL_INITIATING_REQUEST,
            AppState.CALL_OUTGOING_WAITING_ACCEPTANCE,
            AppState.CALL_INCOMING_RINGING,
            AppState.IN_CALL,
            AppState.CALL_TERMINATING_SELF_INITIATED,
            AppState.CALL_REJECTING
        ]

    def _send_hangup_and_begin_ack_wait(self, target_address, 
                                      reason_for_log_and_ui_prefix: str, 
                                      is_rejection_context: bool):
        if not target_address:
            self.log_message(f"_send_hangup_and_begin_ack_wait called with no target_address. Aborting.", is_error=True)
            return

        self.current_hangup_target_address = target_address
        self.hangup_retry_count = 0 
        if is_rejection_context:
            self.pending_call_rejection_ack_address = target_address
        else:
            self.pending_call_rejection_ack_address = None 

        success = self.network_manager.send_packet(SignalType.HANGUP_SIGNAL.value, self.current_hangup_target_address)

        if success:
            self.log_message(f"向 {self.current_hangup_target_address} 发送首次挂断/拒绝信号 ({reason_for_log_and_ui_prefix}). 开始后台静默等待ACK。")
            if self.hangup_ack_timer_id is not None: 
                self.master.after_cancel(self.hangup_ack_timer_id)
                self.hangup_ack_timer_id = None
            
            self.hangup_ack_timer_id = self.master.after(
                HANGUP_ACK_TIMEOUT_MS, 
                self._handle_hangup_ack_timeout 
            )
        else: 
            self.log_message(f"首次发送挂断/拒绝信号至 {self.current_hangup_target_address} 失败。本地立即终止，不会后台重试。", is_error=True)
            self.current_hangup_target_address = None 
            self.pending_call_rejection_ack_address = None

    def _transition_to_call_ended_state(self, target_ended_state: AppState, reason_for_display: str,
                                       peer_address_tuple=None,
                                       cleanup_resources: bool = True,
                                       cancel_active_hangup_retries: bool = True):
        self.log_message(f"Transitioning to ended state: {target_ended_state.name}, Reason: '{reason_for_display}', "
                         f"Cleanup: {cleanup_resources}, CancelRetries: {cancel_active_hangup_retries}")

        if cleanup_resources:
            self._cleanup_active_call_resources()

        if self.call_request_ack_timer_id is not None:
            self.master.after_cancel(self.call_request_ack_timer_id)
            self.call_request_ack_timer_id = None

        if hasattr(self, 'indicator_blinker_timer') and self.indicator_blinker_timer:
            self.indicator_blinker_timer.cancel()

        final_peer_addr = peer_address_tuple
        if not final_peer_addr and self.current_hangup_target_address and cancel_active_hangup_retries:
            final_peer_addr = self.current_hangup_target_address
        elif not final_peer_addr and self.peer_full_address: 
            final_peer_addr = self.peer_full_address

        self._simple_reset_call_vars_and_set_state(
            reason_for_display,
            target_ended_state,
            final_peer_addr, 
            cancel_active_hangup_retries=cancel_active_hangup_retries
        )

    def _terminate_call_session(self, final_state: AppState, reason: str, peer_address, *, send_hangup: bool, is_rejection: bool = False):
        self.log_message(f"Terminating call session. Final State: {final_state.name}, Reason: '{reason}', Send Hangup: {send_hangup}")

        self._cleanup_active_call_resources()

        self.indicator_blinker_timer.cancel()
        if self.call_request_ack_timer_id is not None:
            self.master.after_cancel(self.call_request_ack_timer_id)
            self.call_request_ack_timer_id = None

        if send_hangup and peer_address:
            log_prefix = "已拒绝" if is_rejection else STATUS_LOCALLY_HUNG_UP
            self._send_hangup_and_begin_ack_wait(
                target_address=peer_address,
                reason_for_log_and_ui_prefix=log_prefix,
                is_rejection_context=is_rejection
            )
            self._transition_to_call_ended_state(
                final_state, reason, peer_address,
                cleanup_resources=False, # Already done above
                cancel_active_hangup_retries=False # IMPORTANT
            )
        else:
            self._transition_to_call_ended_state(
                final_state, reason, peer_address,
                cleanup_resources=False, # Already done above
                cancel_active_hangup_retries=True # IMPORTANT
            )

    def handle_local_hangup_action(self):
        current_state = self.app_state
        self.log_message(f"Local hangup action initiated in state: {current_state.name}")

        target_address = self._determine_hangup_target_address(current_state)
        if not target_address:
            self.log_message("Local hangup action, but no target peer. Resetting state.", is_warning=True)
            self._simple_reset_call_vars_and_set_state("操作取消/无通话对象", AppState.IDLE)
            return

        self._play_notification_sound(SOUND_PEER_HANGUP)

        is_rejection = (current_state == AppState.CALL_INCOMING_RINGING)
        if is_rejection:
            reason = f"已拒绝来自 {target_address[0]} 的呼叫"
            final_state = AppState.CALL_ENDED_PEER_REJECTED
        else:
            reason = f"{STATUS_LOCALLY_HUNG_UP} ({target_address[0]})"
            final_state = AppState.CALL_ENDED_LOCALLY_HUNG_UP

        self._terminate_call_session(
            final_state, reason, target_address,
            send_hangup=True, is_rejection=is_rejection
        )

    def handle_peer_hangup(self, addr, reason: str):
        self.log_message(f"Peer hangup received from {addr}. Reason: '{reason}'")
        self._play_notification_sound(SOUND_PEER_HANGUP)

        final_state = AppState.CALL_ENDED_PEER_HUNG_UP
        if STATUS_PEER_REJECTED in reason:
            final_state = AppState.CALL_ENDED_PEER_REJECTED

        self._terminate_call_session(
            final_state, reason, addr, send_hangup=False
        )

    def handle_call_error(self, reason: str, peer_addr):
        self.log_message(f"Call error occurred. Reason: '{reason}', Peer: {peer_addr}", is_error=True)

        final_state = AppState.CALL_ENDED_ERROR
        if "超时" in reason or "失败" in reason:
            final_state = AppState.CALL_ENDED_REQUEST_FAILED

        self._terminate_call_session(
            final_state, reason, peer_addr, send_hangup=True
        )

    def handle_app_closing(self):
        current_state = self.app_state
        target_address = self._determine_hangup_target_address(current_state)

        is_call_context_active = self._is_state_active_or_pending_call(current_state)
        if target_address and is_call_context_active:
            self.log_message("App closing during active/pending call. Attempting one-time HANGUP signal.")
            self._cleanup_active_call_resources()
            self.network_manager.send_packet(SignalType.HANGUP_SIGNAL.value, target_address)

    def _finalize_ui_after_hangup_delay(self):
        timer_id_before_clear = self.final_idle_status_timer_id
        self.final_idle_status_timer_id = None 
        if not (hasattr(self.master, 'winfo_exists') and self.master.winfo_exists()):
            return

        is_truly_ended_state = self.app_state.name.startswith("CALL_ENDED_") and \
                               self.app_state != AppState.CALL_ENDED_APP_CLOSING
        
        no_background_hangup_retries = self.current_hangup_target_address is None

        self.log_message(f"_finalize_ui_after_hangup_delay (timer_id: {timer_id_before_clear}): "
                         f"EndedState={is_truly_ended_state}, NoRetries={no_background_hangup_retries}, "
                         f"CurrentState={self.app_state.name}, HangupTarget={self.current_hangup_target_address}")

        if is_truly_ended_state and no_background_hangup_retries:
            self.log_message(f"3秒延迟后，且无后台挂断/拒绝重试。从 {self.app_state.name} 转换到 IDLE。")
            self._simple_reset_call_vars_and_set_state(
                "",
                AppState.IDLE, 
                None, 
                cancel_active_hangup_retries=True
            )
        elif is_truly_ended_state and not no_background_hangup_retries:
            self.log_message(f"3秒延迟后，但仍有后台挂断/拒绝重试目标: {self.current_hangup_target_address}. "
                             f"UI 保持当前 '{self.app_state.name}' 状态。")
        else:
            self.log_message(f"3秒延迟后，但当前状态 ({self.app_state.name}) 不再是适合转换到IDLE的结束状态，"
                             f"或仍在重试。UI 无变化从此路径。")


    def _handle_call_request_ack_timeout(self):
        self.call_request_ack_timer_id = None 
        if self.app_state == AppState.CALL_INITIATING_REQUEST:
            peer_addr_attempted = self.peer_address_for_call_attempt if self.peer_address_for_call_attempt else ("未知对方", 0)
            reason = f"呼叫请求失败 ({peer_addr_attempted[0]}) - 无应答"
            self.handle_call_error(reason, peer_addr_attempted)
        else:
            self.log_message(f"呼叫请求ACK超时，但状态为 {self.app_state.name}。忽略。")

    def _handle_hangup_ack_timeout(self):
        self.hangup_ack_timer_id = None 

        if not self.current_hangup_target_address or self.app_state == AppState.CALL_ENDED_APP_CLOSING:
            self.log_message(f"挂断/拒绝ACK超时，但无重试目标 ({self.current_hangup_target_address}) 或应用关闭。停止静默重试。")
            if self.current_hangup_target_address:
                self.current_hangup_target_address = None
                self.pending_call_rejection_ack_address = None
            return

        target_address_for_retry = self.current_hangup_target_address
        is_reject_retry = (self.pending_call_rejection_ack_address == target_address_for_retry)
        
        self.hangup_retry_count += 1 
        self.log_message(f"等待来自 {target_address_for_retry} 的{'拒绝' if is_reject_retry else '挂断'}ACK超时。静默后台重试次数: {self.hangup_retry_count}")

        success_resending = self.network_manager.send_packet(SignalType.HANGUP_SIGNAL.value, target_address_for_retry)
        if success_resending:
            self.log_message(f"后台静默重试发送{'拒绝' if is_reject_retry else '挂断'}信号至 {target_address_for_retry} (尝试 {self.hangup_retry_count})")
            if self.hangup_ack_timer_id is not None: 
                self.master.after_cancel(self.hangup_ack_timer_id)
                self.hangup_ack_timer_id = None
            self.hangup_ack_timer_id = self.master.after(
                HANGUP_ACK_TIMEOUT_MS,
                self._handle_hangup_ack_timeout 
            )
        else:
            self.log_message(f"后台静默重试发送{'拒绝' if is_reject_retry else '挂断'}信号失败 (NetworkManager). 将停止此轮对此目标的重试。", is_error=True)
            self.current_hangup_target_address = None # Stop retries for this target if send fails
            self.pending_call_rejection_ack_address = None

    def _revert_indicator_after_deduplication_display(self):
        if self.master.winfo_exists():
            if self.app_state == AppState.IN_CALL:
                self.ui_manager.update_packet_indicator(PACKET_INDICATOR_RED_SENT)
            else: 
                self.ui_manager.update_packet_indicator(PACKET_INDICATOR_IDLE)

    def _handle_audio_deduplication(self):
        if not (hasattr(self.master, 'winfo_exists') and self.master.winfo_exists()):
            return

        if self.app_state == AppState.IN_CALL:
            self.ui_manager.update_packet_indicator(PACKET_INDICATOR_GREEN_ACK)
            duration_seconds = (PYAUDIO_CHUNK / PYAUDIO_RATE * 2) 
            self.indicator_blinker_timer.set(
                duration_seconds,
                self._revert_indicator_after_deduplication_display
            )

    def _play_notification_sound(self, sound_file_name):
        sound_path = resource_path(sound_file_name)
        def play_it():
            try:
                winsound.PlaySound(sound_path, winsound.SND_FILENAME)
            except Exception as e_play:
                self.log_message(f"播放声音 '{sound_file_name}' 时出错 (winsound): {e_play}", is_error=True)
        sound_thread = threading.Thread(target=play_it, daemon=True, name=f"SoundPlayer-{os.path.basename(sound_file_name)}")
        sound_thread.start()

    def _handle_ack_hangup_signal(self, data, addr):
        if self.current_hangup_target_address and addr == self.current_hangup_target_address:
            self.log_message(f"收到来自 {addr} 的挂断/拒绝ACK。停止后台静默重试。")
            if self.hangup_ack_timer_id is not None:
                self.master.after_cancel(self.hangup_ack_timer_id)
                self.hangup_ack_timer_id = None

            acked_peer_addr = self.current_hangup_target_address
            self.current_hangup_target_address = None
            self.pending_call_rejection_ack_address = None
            self.hangup_retry_count = 0

            self.log_message(f"对方 {acked_peer_addr} 已确认我方之前的挂断/拒绝操作。")

            is_relevant_ended_state = self.app_state.name.startswith("CALL_ENDED_") and \
                                      self.app_state != AppState.CALL_ENDED_APP_CLOSING
            
            if is_relevant_ended_state:

                if self.final_idle_status_timer_id is None:
                    self.log_message(f"挂断ACK已收到。之前的3秒转换IDLE定时器已过或不适用。"
                                     f"主动从 {self.app_state.name} 转换到 IDLE。")
                    self._simple_reset_call_vars_and_set_state(
                        "",
                        AppState.IDLE,
                        acked_peer_addr,
                        cancel_active_hangup_retries=True
                    )
        else:
            self.log_message(f"收到来自 {addr} 的挂断/拒绝ACK，但与当前静默重试目标 "
                             f"{self.current_hangup_target_address} 不符或无重试目标。", is_warning=True)

    def _handle_ack_call_request_signal(self, data, addr):
        if self.app_state == AppState.CALL_INITIATING_REQUEST and \
           self.peer_address_for_call_attempt and addr == self.peer_address_for_call_attempt:
            
            self.log_message(f"收到来自 {addr} 的呼叫请求ACK。")
            if self.call_request_ack_timer_id is not None:
                self.master.after_cancel(self.call_request_ack_timer_id)
                self.call_request_ack_timer_id = None

            if self.master.winfo_exists():
                self.master.after(0, self._proceed_with_call_setup, False) 
            else: 
                self._proceed_with_call_setup(False)
        else:
            self.log_message(f"收到来自 {addr} 的意外呼叫请求ACK。当前状态: {self.app_state.name}, "
                             f"期望ACK自: {self.peer_address_for_call_attempt}", is_warning=True)

    def _handle_call_accepted_signal(self, data, addr):
        if self.app_state == AppState.CALL_OUTGOING_WAITING_ACCEPTANCE and \
           self.peer_full_address and addr == self.peer_full_address:
            
            self.log_message(f"收到来自 {addr} 的呼叫接听确认。转换到通话中状态。")
            self._play_notification_sound(SOUND_CALL_CONNECTED)

            my_speaker_status_payload = b"ON" if self.my_speaker_switch_is_on else b"OFF"
            my_speaker_status_signal = SignalType.SPEAKER_STATUS_SIGNAL_PREFIX.value + my_speaker_status_payload
            self.network_manager.send_packet(my_speaker_status_signal, self.peer_full_address)
            self.log_message(f"通话建立(我方呼叫被接听): 已将本机扬声器开关状态 ({my_speaker_status_payload.decode()}) 发送给 {self.peer_full_address}")

            self._set_app_state(AppState.IN_CALL, 
                                reason=f"对方 {addr[0]} 已接听",
                                peer_address_tuple=self.peer_full_address)
        else:
            self.log_message(f"收到来自 {addr} 的意外接听确认。当前状态: {self.app_state.name}, "
                             f"期望对方: {self.peer_full_address}", is_warning=True)

    def _handle_hangup_signal(self, data, addr):
        self.log_message(f"收到来自 {addr} 的 HANGUP_SIGNAL。当前状态: {self.app_state.name}")

        if self.network_manager.send_packet(SignalType.ACK_HANGUP_SIGNAL.value, addr):
            self.log_message(f"已发送挂断ACK至 {addr} (回应收到的HANGUP_SIGNAL)")
        else:
            self.log_message(f"发送挂断ACK至 {addr} 失败 (NetworkManager)", is_warning=True)

        is_relevant_peer_hangup = False
        current_call_peer_addr = self._determine_hangup_target_address(self.app_state)
        
        if current_call_peer_addr and addr == current_call_peer_addr:
            is_relevant_peer_hangup = True
        elif self.app_state == AppState.CALL_OUTGOING_WAITING_ACCEPTANCE and \
             current_call_peer_addr and addr[0] == current_call_peer_addr[0]:
             self.log_message(f"HANGUP from peer IP {addr[0]} but port differs ({addr[1]} vs expected {current_call_peer_addr[1]}). "
                              f"Treating as relevant for CALL_OUTGOING_WAITING_ACCEPTANCE.", is_warning=True)
             is_relevant_peer_hangup = True
        elif self.current_hangup_target_address and addr == self.current_hangup_target_address:
            self.log_message(f"收到对方 {addr} 的HANGUP，而我方正在后台静默重试对该目标的挂断/拒绝。处理为对方挂断。")
            is_relevant_peer_hangup = True
        
        if is_relevant_peer_hangup:
            reason_for_hangup = f"{STATUS_PEER_HUNG_UP} ({addr[0]})"

            if self.app_state in [AppState.CALL_OUTGOING_WAITING_ACCEPTANCE, AppState.CALL_INITIATING_REQUEST]:
                reason_for_hangup = f"{STATUS_PEER_REJECTED} ({addr[0]})"
            elif self.app_state == AppState.CALL_INCOMING_RINGING:
                reason_for_hangup = f"对方 ({addr[0]}) 已取消呼叫"
            
            if self.master.winfo_exists():
                 self.master.after(0, self.handle_peer_hangup, addr, reason_for_hangup)
            else:
                 self.handle_peer_hangup(addr, reason_for_hangup)
        else:
            self.log_message(f"已发送ACK至 {addr}。但收到的挂断信号与当前通话 "
                             f"({current_call_peer_addr[0] if current_call_peer_addr else '无预期'}) 无关，或应用状态 "
                             f"({self.app_state.name}) 或后台重试目标 "
                             f"({self.current_hangup_target_address if self.current_hangup_target_address else '无'}) "
                             f"不处理此来源的挂断。忽略进一步的本地通话状态变更。", is_warning=True)


    def _handle_call_request_signal(self, data, addr):
        eligible_states_for_new_call = [
            AppState.IDLE, AppState.GETTING_PUBLIC_IP_FAILED,
            AppState.CALL_ENDED_LOCALLY_HUNG_UP, AppState.CALL_ENDED_PEER_HUNG_UP,
            AppState.CALL_ENDED_PEER_REJECTED, AppState.CALL_ENDED_ERROR,
            AppState.CALL_ENDED_REQUEST_FAILED
        ]
        if self.app_state not in eligible_states_for_new_call:
            self.log_message(f"当前状态 ({self.app_state.name}) 不接受新呼叫请求，忽略来自 {addr} 的请求。", is_warning=True)
            if self.network_manager.send_packet(SignalType.ACK_CALL_REQUEST_SIGNAL.value, addr):
                self.log_message(f"已发送呼叫请求ACK至 {addr} (但因忙碌忽略呼叫)")
            return

        if self.current_hangup_target_address is not None:
            self.log_message(f"收到新呼叫请求，取消对 {self.current_hangup_target_address} 的先前挂断/拒绝后台静默重试。")
            if self.hangup_ack_timer_id is not None:
                self.master.after_cancel(self.hangup_ack_timer_id)
                self.hangup_ack_timer_id = None
            self.current_hangup_target_address = None
            self.pending_call_rejection_ack_address = None
            self.hangup_retry_count = 0

        if self.network_manager.send_packet(SignalType.ACK_CALL_REQUEST_SIGNAL.value, addr):
            self.log_message(f"已发送呼叫请求ACK至 {addr}")
        else:
            self.log_message(f"发送呼叫请求ACK至 {addr} 失败 (NetworkManager). 无法处理来电。", is_warning=True)
            return 
        
        try:
            self.peer_full_address = addr 

            display_address_tuple = addr 
            self.ui_manager.set_peer_ip_entry(addr[0]) 
            self.ui_manager.set_peer_port_entry(str(addr[1])) 

            self.log_message(f"收到来自 {addr[0]}:{addr[1]} (实际源) 的呼叫请求。")
            
            self._play_notification_sound(SOUND_CALL_CONNECTED) 
            self._set_app_state(AppState.CALL_INCOMING_RINGING,
                                reason=f"收到来自 {display_address_tuple[0]}:{display_address_tuple[1]} 的呼叫",
                                peer_address_tuple=display_address_tuple) 
            
        except Exception as e_call_req:
            self.log_message(f"处理呼叫请求信号时发生未知错误: {e_call_req} - 数据: {data[:40].hex()} from {addr}", is_error=True)
            traceback.print_exc()


    def _handle_audio_data(self, data, addr):
        if self.app_state == AppState.IN_CALL and self.peer_full_address and addr == self.peer_full_address:
            try:
                if len(data) > 4: 
                    seq_num_bytes, audio_payload = data[:4], data[4:]
                    received_seq_num, = struct.unpack("!I", seq_num_bytes) 
                    if audio_payload: 
                        self.audio_manager.write_chunk_to_speaker(audio_payload, received_seq_num)
                else:
                    self.log_message(f"收到过短的音频数据包 (len: {len(data)}) from {addr}", is_warning=True)
            except struct.error as e:
                self.log_message(f"接收音频: 解包序列号错误: {e}. Data len: {len(data)}, Data hex: {data[:10].hex()}", is_warning=True)
            except Exception as e_audio_proc:
                self.log_message(f"处理接收音频时发生未知错误: {e_audio_proc}", is_warning=True)
                traceback.print_exc()

    def _handle_speaker_status_signal(self, data, addr):
        if not (self.app_state == AppState.IN_CALL and self.peer_full_address and addr == self.peer_full_address):
            self.log_message(f"收到来自 {addr} 的扬声器状态信号，但当前状态 ({self.app_state.name}) 或对方地址不匹配。忽略。", is_warning=True)
            return

        try:
            payload = data[len(SignalType.SPEAKER_STATUS_SIGNAL_PREFIX.value):]
            if payload == b"ON":
                self.peer_wants_to_receive_audio = True
                self.log_message(f"对方 {addr} 的扬声器开关已置为 [开启]。我方可以发送音频（如果麦克风也开启）。")
            elif payload == b"OFF":
                self.peer_wants_to_receive_audio = False
                self.log_message(f"对方 {addr} 的扬声器开关已置为 [关闭]。我方将停止发送音频。")
            else:
                self.log_message(f"收到来自 {addr} 的无效扬声器状态负载: {payload}", is_warning=True)
        except Exception as e:
            self.log_message(f"处理扬声器状态信号时发生错误: {e}", is_error=True)
            traceback.print_exc()

    def _on_network_data_received(self, data, addr):
        if data.startswith(SignalType.CALL_REQUEST_SIGNAL_PREFIX.value):
            self._handle_call_request_signal(data, addr)
            return

        if data.startswith(SignalType.SPEAKER_STATUS_SIGNAL_PREFIX.value):
            self._handle_speaker_status_signal(data, addr)
            return

        handler = self._signal_handlers.get(data)
        if handler:
            handler(data, addr)
            return

        if self.app_state == AppState.IN_CALL: 
            self._handle_audio_data(data, addr) 
            return

    def _send_audio_loop_target(self):
            self.log_message("发送线程已启动。")
            read_error_count = 0
            chunk_duration_seconds = PYAUDIO_CHUNK / PYAUDIO_RATE
            last_logged_send_status = None 

            while self.is_running_main_op: 
                if self.app_state != AppState.IN_CALL: 
                    time.sleep(0.02) 
                    read_error_count = 0 
                    last_logged_send_status = None 
                    continue

                should_send_audio = (not self.audio_manager.mic_muted) and self.peer_wants_to_receive_audio

                current_log_key = (self.audio_manager.mic_muted, self.peer_wants_to_receive_audio)
                if current_log_key != last_logged_send_status:
                    if should_send_audio:
                        self.log_message(f"音频发送条件满足: 我方麦克风开启，对方扬声器开关开启。开始发送音频。")
                    else:
                        reason_mic = "我方麦克风静音" if self.audio_manager.mic_muted else "我方麦克风开启"
                        reason_peer_speaker = "对方扬声器开关关闭" if not self.peer_wants_to_receive_audio else "对方扬声器开关开启"
                        self.log_message(f"音频发送条件不满足: ({reason_mic}, {reason_peer_speaker})。暂停发送音频。")
                    last_logged_send_status = current_log_key

                if not should_send_audio:
                    time.sleep(chunk_duration_seconds) 
                    continue

                try:
                    audio_data = self.audio_manager.read_chunk_from_mic()
                    if audio_data is None: 
                        if self.app_state == AppState.IN_CALL: 
                            self.log_message("发送线程：从麦克风读取到None (流可能已关闭或出错)。退出发送循环。", is_warning=True)
                        else:
                            self.log_message(f"发送线程：从麦克风读取到None，但当前状态是 {self.app_state.name} (非IN_CALL)。退出发送循环。", is_warning=True)
                        break
                    
                    read_error_count = 0 

                    if self.app_state != AppState.IN_CALL:
                        self.log_message(f"发送线程: 状态在读取音频后变为 {self.app_state.name} (非IN_CALL)。退出发送循环。", is_warning=True)
                        break 

                    packet_to_send = struct.pack("!I", self.send_sequence_number) + audio_data
                    # Send the packet twice as a simple forward error correction (FEC) mechanism
                    # to mitigate packet loss over UDP.
                    self.network_manager.send_packet(packet_to_send, self.peer_full_address)
                    self.network_manager.send_packet(packet_to_send, self.peer_full_address) 

                    self.send_sequence_number = (self.send_sequence_number + 1) % MAX_SEQ_NUM

                except (IOError, OSError) as e: 
                    if self.app_state == AppState.IN_CALL: 
                        read_error_count += 1
                        self.log_message(f"读取输入流时错误 (IO/OS) ({read_error_count}/{MIC_READ_MAX_ERRORS}): {e}.", is_warning=True)
                        if read_error_count >= MIC_READ_MAX_ERRORS:
                            self.log_message("麦克风连续读取错误过多，终止呼叫。", is_error=True)
                            if self.master.winfo_exists():
                                self.master.after(0, self.handle_call_error, "麦克风连续读取错误", self.peer_full_address)
                            break 
                        time.sleep(0.05) 
                    else:
                        self.log_message(f"发送线程: 读取输入流时错误 (IO/OS) 但状态为 {self.app_state.name}. 错误: {e}. 退出。", is_warning=True)
                        break
                except Exception as e_read_send:
                    log_msg = f"发送线程: 读取/发送音频时发生未知错误: {e_read_send}"
                    if self.app_state == AppState.IN_CALL: 
                        self.log_message(log_msg, is_error=True)
                        traceback.print_exc()
                        if self.master.winfo_exists():
                            self.master.after(0, self.handle_call_error, f"音频发送未知错误: {e_read_send}", self.peer_full_address)
                    else:
                         self.log_message(f"{log_msg} (当前状态: {self.app_state.name})", is_error=True)
                         traceback.print_exc()
                    break 

            self.log_message("发送线程已停止。")

    def _cancel_all_tk_timers(self):
        timers_to_cancel = [
            'final_idle_status_timer_id',
            'call_request_ack_timer_id',
            'hangup_ack_timer_id'
        ]
        for timer_attr_name in timers_to_cancel:
            timer_id = getattr(self, timer_attr_name, None)
            if timer_id is not None:
                if self.master.winfo_exists():
                    try:
                        self.master.after_cancel(timer_id)
                    except Exception:
                        pass
                setattr(self, timer_attr_name, None)

    def _perform_background_cleanup(self, original_state_on_close):
        self.log_message("后台清理线程已启动。")

        self.handle_app_closing()

        if self.send_thread and self.send_thread.is_alive():
            self.log_message("关闭：等待发送线程停止...")
            try:
                self.send_thread.join(timeout=0.5)
            except Exception as e:
                self.log_message(f"发送线程join(on_closing)时出错: {e}")
            if self.send_thread and self.send_thread.is_alive():
                self.log_message("on_closing: 发送线程join超时。", is_warning=True)
        self.send_thread = None

        if hasattr(self, 'network_manager'):
            self.network_manager.stop_listening()
        if hasattr(self, 'audio_manager'):
            self.audio_manager.terminate()

        if hasattr(self, 'indicator_blinker_timer'):
            self.indicator_blinker_timer.stop_thread()

        self.log_message("后台清理完成。安排主窗口销毁。")

        if self.master.winfo_exists():
            self.master.after(0, self.master.destroy)

    def on_closing(self):
        if hasattr(self, '_is_closing') and self._is_closing:
            return
        self._is_closing = True

        self.log_message("正在关闭应用程序... 隐藏窗口并启动后台清理。")
        original_state_on_close = self.app_state

        if self.master.winfo_exists():
            self.master.withdraw()
        if hasattr(self, 'ui_manager'):
            self.ui_manager.unload_custom_font()

        self.is_running_main_op = False
        self._set_app_state(AppState.CALL_ENDED_APP_CLOSING, reason="应用程序关闭")
        self._cancel_all_tk_timers()

        if hasattr(self, 'indicator_blinker_timer'):
            self.indicator_blinker_timer.cancel()

        cleanup_thread = threading.Thread(
            target=self._perform_background_cleanup,
            args=(original_state_on_close,),
            daemon=True,
            name="AppCleanupThread"
        )
        cleanup_thread.start()

if __name__ == "__main__":
    try:
        locale.setlocale(locale.LC_ALL, '') 
    except locale.Error as e:
        print(f"Warning: Could not set system default locale: {e}. Using default 'C' locale.")

    root = ctk.CTk()
    icon_path = resource_path(APP_ICON_FILENAME)
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)
    else:
        print(f"Warning: Icon file not found at {icon_path}")
        
    app = VoiceChatApp(root)
    root.mainloop()