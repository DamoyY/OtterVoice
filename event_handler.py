# event_handler.py

from __future__ import annotations
from typing import TYPE_CHECKING, Callable, Dict

from models import SignalType

if TYPE_CHECKING:
    from state_manager import CallStateManager
    from ui_manager import UIManager
    from audio_manager import AudioManager
    from app_controller import AppController # 新增导入

class EventHandler:
    """
    负责接收所有外部输入（UI、网络、定时器），并将其转换为对 StateManager 或 AppController 的调用。
    这是一个纯粹的“翻译官”。
    """
    def __init__(
        self,
        controller_ref: AppController, # 新增 controller 引用
        state_manager_ref: CallStateManager,
        ui_manager_ref: UIManager,
        audio_manager_ref: AudioManager,
        log_callback: Callable[..., None]
    ):
        self.controller = controller_ref # 新增
        self.state_manager = state_manager_ref
        self.ui_manager = ui_manager_ref
        self.audio_manager = audio_manager_ref
        self.log = log_callback

    def get_ui_callbacks(self) -> Dict[str, Callable]:
        """返回一个包含所有UI回调的完整字典。"""
        return {
            # 核心通话控制
            "ui_on_call_hangup_button_clicked": self.on_call_hangup_button_clicked,
            "ui_on_accept_call": self.on_accept_call_clicked,
            "ui_on_reject_call": self.on_reject_call_clicked,
            "ui_on_toggle_mic": self.on_toggle_mic,
            "ui_on_toggle_speaker": self.on_toggle_speaker,
            
            # 应用级/工具类回调 (新增部分)
            "ui_on_copy_feature_code": self.on_copy_feature_code,
            "ui_on_paste_feature_code": self.on_paste_feature_code,
            "ui_on_toggle_dev_mode": self.on_toggle_dev_mode,
            "ui_on_peer_info_changed": self.on_peer_info_changed,
        }

    # --- 核心通话事件 ---
    def on_call_hangup_button_clicked(self):
        self.state_manager.handle_call_button_press(
            peer_ip=self.ui_manager.get_peer_ip_entry(),
            peer_port=self.ui_manager.get_peer_port_entry(),
            is_peer_info_valid=self.ui_manager.is_peer_info_valid(),
            is_audio_ready=self.audio_manager.is_initialized(),
            is_network_ready=self.controller.is_running_main_op
        )

    def on_accept_call_clicked(self):
        self.state_manager.handle_accept_button_press()

    def on_reject_call_clicked(self):
        self.state_manager.handle_reject_button_press()

    def on_toggle_mic(self):
        mic_muted = self.audio_manager.toggle_mic_mute()
        self.ui_manager.update_mute_switch_text(mic_muted, not self.state_manager.my_speaker_switch_is_on)

    def on_toggle_speaker(self):
        is_on = self.state_manager.toggle_my_speaker_switch()
        self.ui_manager.update_mute_switch_text(self.audio_manager.mic_muted, not is_on)

    # --- 应用级/工具类事件 (新增方法) ---
    def on_copy_feature_code(self):
        self.controller.on_copy_feature_code()

    def on_paste_feature_code(self):
        self.controller.on_paste_feature_code()

    def on_toggle_dev_mode(self):
        self.controller.on_toggle_dev_mode()

    def on_peer_info_changed(self):
        self.controller.on_peer_info_changed()

    # --- 网络事件 ---
    def on_network_data_received(self, data, addr):
        if data.startswith(SignalType.CALL_REQUEST_SIGNAL_PREFIX.value):
            self.state_manager.handle_call_request_signal(addr)
        elif data.startswith(SignalType.SPEAKER_STATUS_SIGNAL_PREFIX.value):
            payload = data[len(SignalType.SPEAKER_STATUS_SIGNAL_PREFIX.value):]
            self.state_manager.handle_speaker_status_signal(payload, addr)
        elif data == SignalType.ACK_HANGUP_SIGNAL.value:
            self.state_manager.handle_ack_hangup_signal(addr)
        elif data == SignalType.ACK_CALL_REQUEST_SIGNAL.value:
            self.state_manager.handle_ack_call_request_signal(addr)
        elif data == SignalType.CALL_ACCEPTED_SIGNAL.value:
            self.state_manager.handle_call_accepted_signal(addr)
        elif data == SignalType.HANGUP_SIGNAL.value:
            self.state_manager.handle_hangup_signal(addr)
        else:
            self.state_manager.handle_audio_data(data, addr)