from __future__ import annotations
import threading
import time
import struct
from typing import TYPE_CHECKING, Callable, Optional, Tuple

from models import AppState, SignalType
from config import *
from utils import resource_path
import winsound

if TYPE_CHECKING:
    import customtkinter as ctk
    from audio_manager import AudioManager
    from network_manager import NetworkManager

class CallStateManager:
    def __init__(
        self,
        master_ref: ctk.CTk,
        audio_manager_ref: AudioManager,
        network_manager_ref: NetworkManager,
        state_change_callback: Callable,
        log_callback: Callable,
    ):
        self.master = master_ref
        self.audio_manager = audio_manager_ref
        self.network_manager = network_manager_ref
        self.on_state_changed = state_change_callback
        self.log = log_callback

        # --- State Variables ---
        self.app_state: AppState = AppState.STARTING
        self.peer_full_address: Optional[Tuple[str, int]] = None
        self.peer_address_for_call_attempt: Optional[Tuple[str, int]] = None
        self.current_hangup_target_address: Optional[Tuple[str, int]] = None
        self.pending_call_rejection_ack_address: Optional[Tuple[str, int]] = None
        self.hangup_retry_count: int = 0
        
        self.send_thread: Optional[threading.Thread] = None
        self.send_sequence_number: int = 0
        
        self.peer_wants_to_receive_audio: bool = True
        self.my_speaker_switch_is_on: bool = True

        # --- Timer IDs ---
        self.call_request_ack_timer_id: Optional[str] = None
        self.hangup_ack_timer_id: Optional[str] = None
        self.final_idle_status_timer_id: Optional[str] = None

    def set_app_state(self, new_state: AppState, reason="", peer_address_tuple=None, associated_data=None):
        old_state = self.app_state
        if old_state == new_state and not reason:
            return
            
        self.app_state = new_state
        self.log(f"状态从 {old_state.name} 变为 {new_state.name}. 原因: '{reason}' "
                 f"对方: {peer_address_tuple if peer_address_tuple else 'N/A'}")

        if new_state == AppState.IN_CALL and old_state != AppState.IN_CALL:
            self._start_in_call_media()
        elif old_state == AppState.IN_CALL and new_state != AppState.IN_CALL:
            self._stop_in_call_media()

        if self.master.winfo_exists():
            self.master.after(0, self.on_state_changed, new_state, reason, peer_address_tuple, associated_data)
        elif self.app_state != AppState.CALL_ENDED_APP_CLOSING:
             self.log(f"Master window does not exist, UI not updated for state {new_state.name}", is_warning=True)

    def handle_call_button_press(self, peer_ip: str, peer_port: str, is_peer_info_valid: bool, is_audio_ready: bool, is_network_ready: bool):
        if self.app_state in [
            AppState.CALL_INITIATING_REQUEST, AppState.CALL_OUTGOING_WAITING_ACCEPTANCE, AppState.IN_CALL
        ]:
            self._handle_local_hangup_action()
        elif self.app_state in [
            AppState.IDLE, AppState.GETTING_PUBLIC_IP_FAILED,
            AppState.CALL_ENDED_LOCALLY_HUNG_UP, AppState.CALL_ENDED_PEER_HUNG_UP,
            AppState.CALL_ENDED_PEER_REJECTED, AppState.CALL_ENDED_ERROR,
            AppState.CALL_ENDED_REQUEST_FAILED
        ]:
            if self.current_hangup_target_address is not None:
                self.log(f"用户尝试新呼叫，取消对 {self.current_hangup_target_address} 的先前挂断/拒绝后台静默重试。")
                if self.hangup_ack_timer_id is not None:
                    self.master.after_cancel(self.hangup_ack_timer_id)
                    self.hangup_ack_timer_id = None
                self.current_hangup_target_address = None
                self.pending_call_rejection_ack_address = None
                self.hangup_retry_count = 0
            
            self.master.after(50, self._initiate_call_sequence, peer_ip, peer_port, is_peer_info_valid, is_audio_ready, is_network_ready)
        else:
            self.log(f"呼叫/挂断按钮按下，但应用状态 ({self.app_state.name}) 不支持操作。")

    def handle_accept_button_press(self):
        if self.app_state == AppState.CALL_INCOMING_RINGING:
            if not self.peer_full_address: 
                self.log("CRITICAL: 尝试接听但 peer_full_address 未设置。", is_error=True)
                self._handle_call_error("内部错误 (接听时无对方地址)", None)
                return

            self.log(f"用户接听了来自 {self.peer_full_address} 的呼叫。")
            self._proceed_with_call_setup(is_accepting_call=True)
        else:
            self.log(f"接听按钮按下，但应用状态 ({self.app_state.name}) 不正确。忽略。", is_warning=True)

    def handle_reject_button_press(self):
        if self.app_state == AppState.CALL_INCOMING_RINGING:
            if not self.peer_full_address:
                self.log("CRITICAL: 尝试拒绝但 peer_full_address 未设置。", is_error=True)
                self._handle_call_error("内部错误 (拒绝时无对方地址)", None)
                return
            
            self.log(f"用户拒绝了来自 {self.peer_full_address} 的呼叫。")
            self._handle_local_hangup_action()
        else:
            self.log(f"拒绝按钮按下，但应用状态 ({self.app_state.name}) 不正确。忽略。", is_warning=True)

    def handle_call_request_ack_timeout(self):
        self.call_request_ack_timer_id = None 
        if self.app_state == AppState.CALL_INITIATING_REQUEST:
            peer_addr_attempted = self.peer_address_for_call_attempt if self.peer_address_for_call_attempt else ("未知对方", 0)
            reason = f"呼叫请求失败 ({peer_addr_attempted[0]}) - 无应答"
            self._handle_call_error(reason, peer_addr_attempted)
        else:
            self.log(f"呼叫请求ACK超时，但状态为 {self.app_state.name}。忽略。")

    def handle_hangup_ack_timeout(self):
        self.hangup_ack_timer_id = None 

        if not self.current_hangup_target_address or self.app_state == AppState.CALL_ENDED_APP_CLOSING:
            if self.current_hangup_target_address:
                self.current_hangup_target_address = None
                self.pending_call_rejection_ack_address = None
            return

        target_address_for_retry = self.current_hangup_target_address
        is_reject_retry = (self.pending_call_rejection_ack_address == target_address_for_retry)
        
        self.hangup_retry_count += 1 
        self.log(f"等待来自 {target_address_for_retry} 的{'拒绝' if is_reject_retry else '挂断'}ACK超时。静默后台重试次数: {self.hangup_retry_count}")

        if self.network_manager.send_packet(SignalType.HANGUP_SIGNAL.value, target_address_for_retry):
            self.hangup_ack_timer_id = self.master.after(HANGUP_ACK_TIMEOUT_MS, self.handle_hangup_ack_timeout)
        else:
            self.log(f"后台静默重试发送信号失败 (NetworkManager). 将停止此轮对此目标的重试。", is_error=True)
            self.current_hangup_target_address = None
            self.pending_call_rejection_ack_address = None

    def handle_app_closing(self):
        target_address = self._determine_hangup_target_address()
        is_call_active = self.app_state in [
            AppState.CALL_INITIATING_REQUEST, AppState.CALL_OUTGOING_WAITING_ACCEPTANCE,
            AppState.CALL_INCOMING_RINGING, AppState.IN_CALL,
            AppState.CALL_TERMINATING_SELF_INITIATED, AppState.CALL_REJECTING
        ]
        if target_address and is_call_active:
            self.log("App closing during active call. Attempting one-time HANGUP signal.")
            self._cleanup_active_call_resources()
            self.network_manager.send_packet(SignalType.HANGUP_SIGNAL.value, target_address)

    def cleanup_for_closing(self):
        self.set_app_state(AppState.CALL_ENDED_APP_CLOSING, reason="应用程序关闭")
        timers_to_cancel = [self.call_request_ack_timer_id, self.hangup_ack_timer_id, self.final_idle_status_timer_id]
        for timer_id in timers_to_cancel:
            if timer_id:
                try:
                    self.master.after_cancel(timer_id)
                except Exception:
                    pass
        
        if self.send_thread and self.send_thread.is_alive():
            self.log("关闭：等待发送线程停止...")
            self.send_thread.join(timeout=0.5)

    def handle_ack_hangup_signal(self, addr):
        if self.current_hangup_target_address and addr == self.current_hangup_target_address:
            self.log(f"收到来自 {addr} 的挂断/拒绝ACK。停止后台静默重试。")
            if self.hangup_ack_timer_id is not None:
                self.master.after_cancel(self.hangup_ack_timer_id)
                self.hangup_ack_timer_id = None

            acked_peer_addr = self.current_hangup_target_address
            self.current_hangup_target_address = None
            self.pending_call_rejection_ack_address = None
            self.hangup_retry_count = 0

            if self.app_state.name.startswith("CALL_ENDED_") and self.final_idle_status_timer_id is None:
                self._simple_reset_call_vars_and_set_state("", AppState.IDLE, acked_peer_addr)
        else:
            self.log(f"收到来自 {addr} 的意外挂断ACK。", is_warning=True)

    def handle_ack_call_request_signal(self, addr):
        if self.app_state == AppState.CALL_INITIATING_REQUEST and self.peer_address_for_call_attempt and addr == self.peer_address_for_call_attempt:
            self.log(f"收到来自 {addr} 的呼叫请求ACK。")
            if self.call_request_ack_timer_id is not None:
                self.master.after_cancel(self.call_request_ack_timer_id)
                self.call_request_ack_timer_id = None
            self._proceed_with_call_setup(is_accepting_call=False)
        else:
            self.log(f"收到来自 {addr} 的意外呼叫请求ACK。", is_warning=True)

    def handle_call_accepted_signal(self, addr):
        if self.app_state == AppState.CALL_OUTGOING_WAITING_ACCEPTANCE and self.peer_full_address and addr == self.peer_full_address:
            self.log(f"收到来自 {addr} 的呼叫接听确认。")
            self._play_notification_sound(SOUND_CALL_CONNECTED)
            self._send_my_speaker_status()
            self.set_app_state(AppState.IN_CALL, reason=f"对方 {addr[0]} 已接听", peer_address_tuple=self.peer_full_address)
        else:
            self.log(f"收到来自 {addr} 的意外接听确认。", is_warning=True)

    def handle_hangup_signal(self, addr):
        self.log(f"收到来自 {addr} 的 HANGUP_SIGNAL。")
        self.network_manager.send_packet(SignalType.ACK_HANGUP_SIGNAL.value, addr)

        current_call_peer_addr = self._determine_hangup_target_address()
        is_relevant = (current_call_peer_addr and addr == current_call_peer_addr) or \
                      (self.current_hangup_target_address and addr == self.current_hangup_target_address)
        
        if is_relevant:
            reason = f"{STATUS_PEER_HUNG_UP} ({addr[0]})"
            if self.app_state in [AppState.CALL_OUTGOING_WAITING_ACCEPTANCE, AppState.CALL_INITIATING_REQUEST]:
                reason = f"{STATUS_PEER_REJECTED} ({addr[0]})"
            elif self.app_state == AppState.CALL_INCOMING_RINGING:
                reason = f"对方 ({addr[0]}) 已取消呼叫"
            self._handle_peer_hangup(addr, reason)
        else:
            self.log(f"收到的挂断信号与当前通话无关，忽略。", is_warning=True)

    def handle_call_request_signal(self, addr):
        eligible_states = [
            AppState.IDLE, AppState.GETTING_PUBLIC_IP_FAILED,
            AppState.CALL_ENDED_LOCALLY_HUNG_UP, AppState.CALL_ENDED_PEER_HUNG_UP,
            AppState.CALL_ENDED_PEER_REJECTED, AppState.CALL_ENDED_ERROR,
            AppState.CALL_ENDED_REQUEST_FAILED
        ]
        if self.app_state not in eligible_states:
            self.log(f"当前状态 ({self.app_state.name}) 忙，忽略来自 {addr} 的呼叫请求。", is_warning=True)
            self.network_manager.send_packet(SignalType.ACK_CALL_REQUEST_SIGNAL.value, addr)
            return

        if self.current_hangup_target_address:
            if self.hangup_ack_timer_id: self.master.after_cancel(self.hangup_ack_timer_id)
            self.current_hangup_target_address = None

        if self.network_manager.send_packet(SignalType.ACK_CALL_REQUEST_SIGNAL.value, addr):
            self.peer_full_address = addr
            self._play_notification_sound(SOUND_CALL_CONNECTED) 
            self.set_app_state(AppState.CALL_INCOMING_RINGING, reason=f"收到来自 {addr[0]} 的呼叫", peer_address_tuple=addr)
        else:
            self.log(f"发送呼叫请求ACK至 {addr} 失败，无法处理来电。", is_warning=True)

    def handle_audio_data(self, data, addr):
        if self.app_state == AppState.IN_CALL and self.peer_full_address and addr == self.peer_full_address:
            try:
                if len(data) > 4:
                    seq_num_bytes, audio_payload = data[:4], data[4:]
                    received_seq_num, = struct.unpack("!I", seq_num_bytes)
                    if audio_payload:
                        self.audio_manager.write_chunk_to_speaker(audio_payload, received_seq_num)
            except Exception as e:
                self.log(f"处理接收音频时发生错误: {e}", is_warning=True)

    def handle_speaker_status_signal(self, payload, addr):
        if self.app_state == AppState.IN_CALL and self.peer_full_address and addr == self.peer_full_address:
            if payload == b"ON":
                self.peer_wants_to_receive_audio = True
                self.log(f"对方 {addr} 的扬声器已开启。")
            elif payload == b"OFF":
                self.peer_wants_to_receive_audio = False
                self.log(f"对方 {addr} 的扬声器已关闭。")

    def toggle_my_speaker_switch(self):
        self.my_speaker_switch_is_on = not self.my_speaker_switch_is_on
        self.log(f"本机扬声器开关已切换为: {'开启' if self.my_speaker_switch_is_on else '关闭'}")
        if self.app_state == AppState.IN_CALL:
            self._send_my_speaker_status()
        return self.my_speaker_switch_is_on

    def _initiate_call_sequence(self, peer_ip, peer_port, is_peer_info_valid, is_audio_ready, is_network_ready):
        if not is_audio_ready:
            self.set_app_state(AppState.GETTING_PUBLIC_IP_FAILED, reason="PyAudio错误，无法呼叫。") 
            return
        if not is_network_ready: return
        if not is_peer_info_valid: return

        self.peer_address_for_call_attempt = (peer_ip, int(peer_port))
        self.set_app_state(AppState.CALL_INITIATING_REQUEST, reason=f"向 {self.peer_address_for_call_attempt} 发送呼叫请求", peer_address_tuple=self.peer_address_for_call_attempt)

        self.call_request_ack_timer_id = self.master.after(CALL_REQUEST_ACK_TIMEOUT_MS, self.handle_call_request_ack_timeout)

        if not self.network_manager.send_packet(SignalType.CALL_REQUEST_SIGNAL_PREFIX.value, self.peer_address_for_call_attempt):
            self.master.after_cancel(self.call_request_ack_timer_id)
            self.call_request_ack_timer_id = None
            self._transition_to_call_ended_state(AppState.CALL_ENDED_REQUEST_FAILED, "呼叫请求发送错误", self.peer_address_for_call_attempt, cleanup_resources=False)

    def _proceed_with_call_setup(self, is_accepting_call=False):
        if not is_accepting_call:
            self.peer_full_address = self.peer_address_for_call_attempt
            self.peer_address_for_call_attempt = None
        
        if not self.peer_full_address:
            self._transition_to_call_ended_state(AppState.CALL_ENDED_ERROR, "内部呼叫错误 (无对方地址)")
            return

        self.peer_wants_to_receive_audio = True
        self.my_speaker_switch_is_on = True
        self.send_sequence_number = 0
        self.audio_manager.clear_played_sequence_numbers()

        if is_accepting_call:
            self.network_manager.send_packet(SignalType.CALL_ACCEPTED_SIGNAL.value, self.peer_full_address)
            self._send_my_speaker_status()
            self._play_notification_sound(SOUND_CALL_CONNECTED)
            self.set_app_state(AppState.IN_CALL, reason=f"已接听来自 {self.peer_full_address[0]} 的呼叫", peer_address_tuple=self.peer_full_address)
        else:
            self.set_app_state(AppState.CALL_OUTGOING_WAITING_ACCEPTANCE, reason=f"等待 {self.peer_full_address[0]} 接听", peer_address_tuple=self.peer_full_address)

    def _send_my_speaker_status(self):
        if self.peer_full_address:
            status_payload = b"ON" if self.my_speaker_switch_is_on else b"OFF"
            signal = SignalType.SPEAKER_STATUS_SIGNAL_PREFIX.value + status_payload
            self.network_manager.send_packet(signal, self.peer_full_address)

    def _handle_local_hangup_action(self):
        target_address = self._determine_hangup_target_address()
        if not target_address:
            self._simple_reset_call_vars_and_set_state("操作取消/无通话对象", AppState.IDLE, peer_addr=None)
            return
        self._play_notification_sound(SOUND_PEER_HANGUP)
        is_rejection = (self.app_state == AppState.CALL_INCOMING_RINGING)
        reason = f"已拒绝来自 {target_address[0]} 的呼叫" if is_rejection else f"{STATUS_LOCALLY_HUNG_UP} ({target_address[0]})"
        final_state = AppState.CALL_ENDED_PEER_REJECTED if is_rejection else AppState.CALL_ENDED_LOCALLY_HUNG_UP
        self._terminate_call_session(final_state, reason, target_address, send_hangup=True, is_rejection=is_rejection)

    def _handle_peer_hangup(self, addr, reason: str):
        self._play_notification_sound(SOUND_PEER_HANGUP)
        final_state = AppState.CALL_ENDED_PEER_REJECTED if STATUS_PEER_REJECTED in reason else AppState.CALL_ENDED_PEER_HUNG_UP
        self._terminate_call_session(final_state, reason, addr, send_hangup=False)

    def _handle_call_error(self, reason: str, peer_addr):
        self.log(f"Call error: '{reason}', Peer: {peer_addr}", is_error=True)
        should_send_hangup = self.app_state != AppState.CALL_INITIATING_REQUEST
        final_state = AppState.CALL_ENDED_REQUEST_FAILED if "超时" in reason or "失败" in reason else AppState.CALL_ENDED_ERROR
        self._terminate_call_session(final_state, reason, peer_addr, send_hangup=should_send_hangup)

    def _terminate_call_session(self, final_state: AppState, reason: str, peer_address, *, send_hangup: bool, is_rejection: bool = False):
        self._cleanup_active_call_resources()
        if self.call_request_ack_timer_id: self.master.after_cancel(self.call_request_ack_timer_id)

        if send_hangup and peer_address:
            self._send_hangup_and_begin_ack_wait(peer_address, is_rejection)
            self._transition_to_call_ended_state(final_state, reason, peer_address, cleanup_resources=False, cancel_active_hangup_retries=False)
        else:
            self._transition_to_call_ended_state(final_state, reason, peer_address, cleanup_resources=False, cancel_active_hangup_retries=True)

    def _transition_to_call_ended_state(self, target_ended_state: AppState, reason: str, peer_address_tuple=None, cleanup_resources: bool = True, cancel_active_hangup_retries: bool = True):
        if cleanup_resources: self._cleanup_active_call_resources()
        if self.call_request_ack_timer_id: self.master.after_cancel(self.call_request_ack_timer_id)
        
        final_peer_addr = peer_address_tuple or self.current_hangup_target_address or self.peer_full_address
        self._simple_reset_call_vars_and_set_state(reason, target_ended_state, final_peer_addr, cancel_active_hangup_retries=cancel_active_hangup_retries)

        if target_ended_state != AppState.CALL_ENDED_APP_CLOSING:
            if self.final_idle_status_timer_id: self.master.after_cancel(self.final_idle_status_timer_id)
            self.final_idle_status_timer_id = self.master.after(CALL_END_UI_RESET_DELAY_MS, self._finalize_ui_after_hangup_delay)

    def _finalize_ui_after_hangup_delay(self):
        self.final_idle_status_timer_id = None 
        if self.app_state.name.startswith("CALL_ENDED_") and self.current_hangup_target_address is None:
            self.set_app_state(AppState.IDLE, "通话结束，恢复空闲")

    def _simple_reset_call_vars_and_set_state(self, reason, target_state, peer_addr, *, cancel_active_hangup_retries=True):
        self.peer_full_address = None
        self.peer_address_for_call_attempt = None
        self.peer_wants_to_receive_audio = True
        self.my_speaker_switch_is_on = True

        if cancel_active_hangup_retries:
            if self.hangup_ack_timer_id: self.master.after_cancel(self.hangup_ack_timer_id)
            self.current_hangup_target_address = None
            self.pending_call_rejection_ack_address = None
            self.hangup_retry_count = 0
        self.set_app_state(target_state, reason=reason, peer_address_tuple=peer_addr)

    def _send_hangup_and_begin_ack_wait(self, target_address, is_rejection_context: bool):
        self.current_hangup_target_address = target_address
        self.hangup_retry_count = 0 
        self.pending_call_rejection_ack_address = target_address if is_rejection_context else None

        if self.network_manager.send_packet(SignalType.HANGUP_SIGNAL.value, self.current_hangup_target_address):
            if self.hangup_ack_timer_id: self.master.after_cancel(self.hangup_ack_timer_id)
            self.hangup_ack_timer_id = self.master.after(HANGUP_ACK_TIMEOUT_MS, self.handle_hangup_ack_timeout)
        else: 
            self.current_hangup_target_address = None
            self.pending_call_rejection_ack_address = None

    def _cleanup_active_call_resources(self):
        if self.app_state != AppState.IN_CALL:
            self._stop_in_call_media()

    def _determine_hangup_target_address(self):
        state = self.app_state
        if state in [AppState.IN_CALL, AppState.CALL_OUTGOING_WAITING_ACCEPTANCE, AppState.CALL_INCOMING_RINGING]:
            return self.peer_full_address
        elif state == AppState.CALL_INITIATING_REQUEST:
            return self.peer_address_for_call_attempt
        return self.current_hangup_target_address

    def _play_notification_sound(self, sound_file_name):
        sound_path = resource_path(sound_file_name)
        threading.Thread(target=lambda: winsound.PlaySound(sound_path, winsound.SND_FILENAME), daemon=True).start()

    def _start_in_call_media(self):
        self.log("媒体会话启动：打开音频流并启动发送线程。")
        if not self.audio_manager.open_input_stream():
            self._handle_call_error("麦克风打开失败", self.peer_full_address)
            return
        if not self.audio_manager.open_output_stream():
            self._handle_call_error("扬声器打开失败", self.peer_full_address)
            return

        self.send_thread = threading.Thread(target=self._send_audio_loop_target, daemon=True, name="SendAudioThread")
        self.send_thread.start()

    def _stop_in_call_media(self):
        self.log("媒体会话停止：关闭音频流并停止发送线程。")
        self.audio_manager.close_input_stream()
        self.audio_manager.close_output_stream()
        self.audio_manager.clear_played_sequence_numbers()
        if self.send_thread and self.send_thread.is_alive():
            self.send_thread.join(timeout=0.25)
        self.send_thread = None

    def _send_audio_loop_target(self):
        self.log("发送线程已启动。")
        read_error_count = 0
        while self.app_state == AppState.IN_CALL:
            should_send = (not self.audio_manager.mic_muted) and self.peer_wants_to_receive_audio
            if not should_send:
                time.sleep(PYAUDIO_CHUNK / PYAUDIO_RATE)
                continue
            try:
                audio_data = self.audio_manager.read_chunk_from_mic()
                if audio_data is None: break
                packet = struct.pack("!I", self.send_sequence_number) + audio_data
                self.network_manager.send_packet(packet, self.peer_full_address)
                self.network_manager.send_packet(packet, self.peer_full_address) # FEC
                self.send_sequence_number = (self.send_sequence_number + 1) % MAX_SEQ_NUM
            except (IOError, OSError) as e: 
                read_error_count += 1
                if read_error_count >= MIC_READ_MAX_ERRORS:
                    self.log("麦克风连续读取错误过多，终止呼叫。", is_error=True)
                    self.master.after(0, self._handle_call_error, "麦克风连续读取错误", self.peer_full_address)
                    break 
            except Exception as e:
                self.log(f"发送线程发生未知错误: {e}", is_error=True)
                self.master.after(0, self._handle_call_error, f"音频发送未知错误", self.peer_full_address)
                break 
        self.log("发送线程已停止。")