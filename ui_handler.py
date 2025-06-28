from __future__ import annotations
from models import AppState
from config import *
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state_manager import CallStateManager
    from ui_manager import UIManager
    from app_controller import AppController

class UIStateHandler:
    def __init__(
        self,
        ui_manager_ref: UIManager,
        state_manager_ref: CallStateManager,
        controller_ref: AppController
    ):
        self.ui_manager = ui_manager_ref
        self.state_manager = state_manager_ref
        self.controller = controller_ref

        self._ui_state_handlers = {
            AppState.STARTING: self.update_ui_for_starting_state,
            AppState.INITIALIZING_NETWORK: self.update_ui_for_initializing_network_state,
            AppState.GETTING_PUBLIC_IP_FAILED: self.update_ui_for_getting_public_ip_failed_state,
            AppState.IDLE: self.update_ui_for_idle_state,
            AppState.CALL_INITIATING_REQUEST: self.update_ui_for_call_initiating_request_state,
            AppState.CALL_OUTGOING_WAITING_ACCEPTANCE: self.update_ui_for_call_outgoing_waiting_acceptance_state,
            AppState.CALL_INCOMING_RINGING: self.update_ui_for_call_incoming_ringing_state,
            AppState.IN_CALL: self.update_ui_for_in_call_state,
            AppState.CALL_TERMINATING_SELF_INITIATED: self.update_ui_for_call_terminating_self_initiated_state,
            AppState.CALL_REJECTING: self.update_ui_for_call_rejecting_state,
            AppState.CALL_ENDED_LOCALLY_HUNG_UP: self.update_ui_for_call_ended_state,
            AppState.CALL_ENDED_PEER_HUNG_UP: self.update_ui_for_call_ended_state,
            AppState.CALL_ENDED_PEER_REJECTED: self.update_ui_for_call_ended_state,
            AppState.CALL_ENDED_ERROR: self.update_ui_for_call_ended_state,
            AppState.CALL_ENDED_REQUEST_FAILED: self.update_ui_for_call_ended_state,
            AppState.CALL_ENDED_APP_CLOSING: self.update_ui_for_call_ended_app_closing_state,
        }

    def get_peer_display_name_for_ui(self, current_peer_address_tuple=None):
        addr = current_peer_address_tuple or self.state_manager.peer_full_address or \
               self.state_manager.peer_address_for_call_attempt or self.state_manager.current_hangup_target_address
        if addr: return f"{addr[0]}:{addr[1]}"
        
        _ip = self.ui_manager.get_peer_ip_entry()
        _port = self.ui_manager.get_peer_port_entry()
        if _ip and _port: return f"{_ip}:{_port}"
        
        return "对方"

    def update_ui_elements_for_state(self, new_state, reason="", peer_address_tuple=None, associated_data=None):
        if not self.ui_manager.master.winfo_exists(): return

        handler = self._ui_state_handlers.get(new_state, self.update_ui_for_unknown_state)
        ui_config = handler(reason, peer_address_tuple, associated_data)
        self.ui_manager.apply_ui_config(ui_config, new_state)

    def update_ui_for_starting_state(self, *args):
        return {"status_message": "正在启动...", "status_color": COLOR_STATUS_INFO, "call_btn_state": "disabled"}

    def update_ui_for_initializing_network_state(self, reason, *args):
        return {"status_message": reason or "正在初始化网络...", "status_color": COLOR_STATUS_INFO, "call_btn_state": "disabled"}
        
    def update_ui_for_getting_public_ip_failed_state(self, reason, *args):
        status_message = reason or "公网地址获取失败"
        if self.controller.audio_manager.is_initialized():
            status_message = "公网IP获取失败, 但仍可尝试呼叫/接收。" if self.ui_manager.is_peer_info_valid() else "公网IP获取失败, 且无远端信息。"
        return {"status_message": status_message, "status_color": COLOR_STATUS_ERROR, "parse_btn_enabled": True, "call_btn_state": "normal" if self.ui_manager.is_peer_info_valid() else "disabled"}

    def update_ui_for_idle_state(self, *args):
        status_message = STATUS_WAITING_FOR_REMOTE_INFO
        call_btn_state = "disabled"
        if self.ui_manager.is_peer_info_valid():
            status_message = STATUS_READY_TO_CALL_OR_RECEIVE
            if self.controller.audio_manager.is_initialized() and self.controller.is_running_main_op:
                call_btn_state = "normal"
        return {"status_message": status_message, "status_color": COLOR_STATUS_INFO, "parse_btn_enabled": True, "call_btn_state": call_btn_state}

    def update_ui_for_call_active_states_base(self, peer_address_tuple, status_template, status_color, packet_indicator_color=None):
        peer_name = self.get_peer_display_name_for_ui(peer_address_tuple)
        return {
            "call_btn_text": "挂断", "call_btn_fg_color": COLOR_BUTTON_REJECT_BG, "call_btn_hover_color": COLOR_BUTTON_REJECT_HOVER_BG,
            "call_btn_state": "normal", "parse_btn_enabled": False,
            "status_message": status_template.format(peer_display_name=peer_name), "status_color": status_color,
            "packet_indicator_color_override": packet_indicator_color
        }

    def update_ui_for_call_initiating_request_state(self, reason, peer_addr, *args):
        return self.update_ui_for_call_active_states_base(peer_addr, f"{STATUS_SENDING_CALL_REQUEST} ({{peer_display_name}})", COLOR_STATUS_CALLING)

    def update_ui_for_call_outgoing_waiting_acceptance_state(self, reason, peer_addr, *args):
        return self.update_ui_for_call_active_states_base(peer_addr, "正在呼叫 {peer_display_name}... (等待对方接听)", COLOR_STATUS_CALLING)

    def update_ui_for_in_call_state(self, reason, peer_addr, *args):
        return self.update_ui_for_call_active_states_base(peer_addr, "通话中 - {peer_display_name}", COLOR_STATUS_SUCCESS, PACKET_INDICATOR_RED_SENT)

    def update_ui_for_call_incoming_ringing_state(self, reason, peer_addr, *args):
        if peer_addr:
            self.ui_manager.set_peer_ip_entry(peer_addr[0])
            self.ui_manager.set_peer_port_entry(str(peer_addr[1]))
            
        peer_name = self.get_peer_display_name_for_ui(peer_addr)
        return {"status_message": f"收到来自 {peer_name} 的呼叫", "status_color": COLOR_STATUS_INFO, "parse_btn_enabled": False}

    def update_ui_for_call_terminating_self_initiated_state(self, reason, peer_addr, *args):
        return self.update_ui_for_call_ended_state(reason or f"{STATUS_LOCALLY_HUNG_UP} ({self.get_peer_display_name_for_ui(peer_addr)})", peer_addr, *args)

    def update_ui_for_call_rejecting_state(self, reason, peer_addr, *args):
        return self.update_ui_for_call_ended_state(f"已拒绝来自 {self.get_peer_display_name_for_ui(peer_addr)} 的呼叫", peer_addr, *args)

    def update_ui_for_call_ended_state(self, reason, peer_addr, *args):
        if peer_addr:
            self.ui_manager.set_peer_ip_entry(peer_addr[0])
            self.ui_manager.set_peer_port_entry(str(peer_addr[1]))

        current_state = self.state_manager.app_state
        status_color = COLOR_STATUS_DEFAULT
        if current_state == AppState.CALL_ENDED_LOCALLY_HUNG_UP: status_color = COLOR_STATUS_SUCCESS
        elif current_state in [AppState.CALL_ENDED_PEER_HUNG_UP, AppState.CALL_ENDED_PEER_REJECTED]: status_color = COLOR_STATUS_WARNING
        elif current_state in [AppState.CALL_ENDED_ERROR, AppState.CALL_ENDED_REQUEST_FAILED]: status_color = COLOR_STATUS_ERROR
        
        can_call_again = self.ui_manager.is_peer_info_valid() and self.controller.audio_manager.is_initialized() and self.controller.is_running_main_op
        return {"parse_btn_enabled": True, "status_message": reason or "通话已结束", "status_color": status_color, "call_btn_state": "normal" if can_call_again else "disabled"}

    def update_ui_for_call_ended_app_closing_state(self, *args):
        return {"status_message": "程序正在关闭...", "status_color": COLOR_STATUS_INFO, "call_btn_state": "disabled", "parse_btn_enabled": False}
        
    def update_ui_for_unknown_state(self, *args):
        self.controller.log_message(f"警告: 未知的UI状态处理: {self.state_manager.app_state.name}", is_warning=True)
        return {"status_message": "状态未知", "status_color": COLOR_STATUS_DEFAULT, "call_btn_state": "disabled"}