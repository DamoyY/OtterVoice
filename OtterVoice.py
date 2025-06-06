print("Starting up")

# --- 应用与UI配置 (Application & UI Configuration) ---
APP_NAME = "Otter Voice"
APP_ICON_FILENAME = 'image__2__o6e_icon.ico'
INITIAL_WINDOW_WIDTH = 550
INITIAL_WINDOW_HEIGHT = 335
DEV_MODE_HEIGHT_INCREASE = 300

# 字体配置 (Font Configuration)
DESIRED_FONT_FAMILY = "思源黑体"
DESIRED_FONT_FILENAME = "SourceHanSansSC-Regular.otf"
DEFAULT_FALLBACK_FONT = "Roboto"
FONT_SIZE_LABEL = 13
FONT_SIZE_TEXTBOX = 11
FONT_SIZE_STATUS = 12
FONT_SIZE_TITLE = 22

# 声音文件 (Sound Files)
SOUND_CALL_CONNECTED = "notification_call.wav"
SOUND_PEER_HANGUP = "notification_hangup.wav"

# UI颜色主题 (UI Color Theme)
COLOR_TEXT_DEFAULT = ("#FFFFFF", "#FFFFFF")
COLOR_TEXT_MUTED = ("gray50", "gray50")
COLOR_STATUS_DEFAULT = ("gray60", "gray40")
COLOR_STATUS_INFO = ("#1E88E5", "#42A5F5")
COLOR_STATUS_SUCCESS = ("#43A047", "#66BB6A")
COLOR_STATUS_WARNING = ("#FFA000", "#FFCA28")
COLOR_STATUS_ERROR = ("#D32F2F", "#EF5350")
COLOR_STATUS_CALLING = ("#FF8C00", "#FFA500")
COLOR_BUTTON_CALL_FG = ("#FFFFFF", "#FFFFFF")
COLOR_BUTTON_ACCEPT_BG = ("#4CAF50", "#66BB6A")
COLOR_BUTTON_REJECT_BG = ("#F44336", "#EF5350")
COLOR_BUTTON_ACCEPT_HOVER_BG = ("#409443", "#59A85C")
COLOR_BUTTON_REJECT_HOVER_BG = ("#D32F2F", "#D73F3F")
PACKET_INDICATOR_GREEN_ACK = "#00FF00"
PACKET_INDICATOR_RED_SENT = "#FF0000"
PACKET_INDICATOR_IDLE = "gray50"


# --- 网络与协议配置 (Network & Protocol Configuration) ---
# STUN服务器
DEFAULT_STUN_HOST = 'stun.miwifi.com'
DEFAULT_STUN_PORT = 3478

# 功能码密钥 (Feature Code Key)
FEATURE_CODE_KEY = "P2PKey!VoIP"

# 网络参数 (Networking Parameters)
MAX_PACKET_SIZE = 4096
RANDOM_PORT_START = 49152
RANDOM_PORT_END = 65535
RANDOM_PORT_MAX_TRIES = 100

# 超时设置 (Timeouts in Milliseconds)
CALL_REQUEST_ACK_TIMEOUT_MS = 500
HANGUP_ACK_TIMEOUT_MS = 500
CALL_END_UI_RESET_DELAY_MS = 3000

# --- 音频配置 (Audio Configuration) ---
import pyaudio
PYAUDIO_FORMAT = pyaudio.paInt16
PYAUDIO_CHANNELS = 1
PYAUDIO_RATE = 40000
PYAUDIO_CHUNK = 256
MAX_SEQ_NUM = 2**32
SEQ_NUM_DEQUE_MAXLEN = 200
MIC_READ_MAX_ERRORS = 20

# --- UI 静态文本 (UI Static Text) ---
# 这些文本用于 AppState.IDLE/GETTING_PUBLIC_IP_FAILED 时的多部分状态显示
STATUS_WAITING_FOR_REMOTE_INFO = "未有远端特征/已可接收呼叫"
STATUS_READY_TO_CALL_OR_RECEIVE = "已可发出呼叫/已可接收呼叫"
STATUS_SENDING_CALL_REQUEST = "正在发送呼叫请求..."
STATUS_LOCALLY_HUNG_UP = "已主动挂断"
STATUS_PEER_HUNG_UP = "对方已挂断"
STATUS_PEER_REJECTED = "对方已拒绝"



import socket
import threading
import customtkinter as ctk
from customtkinter import ThemeManager
from tkinter import messagebox
import time
import sys
import locale
import struct
import random
import base64
from collections import deque
import datetime
from enum import Enum, auto
import os
import traceback
import winsound
import ctypes
from ctypes import wintypes
print("Imports done")

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

class SingleThreadPreciseTimer:
    def __init__(self, master, name="PreciseTimerThread"):
        self.master = master
        self._target_time_monotonic = None
        self._callback = None
        self._args = None
        self._active = False
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._thread_should_stop = False
        self._thread = threading.Thread(target=self._run, daemon=True, name=name)
        self._thread.start()

    def _run(self):
        while True:
            callback_to_run = None
            args_to_run = None

            with self._lock:
                if self._thread_should_stop:
                    break

                if not self._active or self._target_time_monotonic is None:
                    self._condition.wait()
                    continue

                current_time_monotonic = time.monotonic()
                wait_duration = self._target_time_monotonic - current_time_monotonic

                if wait_duration <= 0:
                    if self._active:
                        callback_to_run = self._callback
                        args_to_run = self._args if self._args is not None else []

                        self._active = False 
                        self._target_time_monotonic = None
                        self._callback = None
                        self._args = None
                else:
                    self._condition.wait(timeout=wait_duration)
                    continue 

            if callback_to_run:
                if self.master.winfo_exists():
                    self.master.after(0, callback_to_run, *args_to_run)

    def set(self, delay_seconds_float, callback, *args):
        if not callable(callback):
            raise TypeError("callback must be callable")
        if not (isinstance(delay_seconds_float, (int, float)) and delay_seconds_float >= 0):
            raise ValueError("delay_seconds_float must be a non-negative number")

        with self._lock:
            self._target_time_monotonic = time.monotonic() + delay_seconds_float
            self._callback = callback
            self._args = args
            self._active = True
            self._condition.notify()

    def cancel(self):
        with self._lock:
            self._active = False
            self._target_time_monotonic = None
            self._callback = None
            self._args = None
            self._condition.notify()
    def is_active(self):
        with self._lock:
            return self._active

    def stop_thread(self):
        with self._lock:
            self._thread_should_stop = True
            self._active = False
            self._condition.notify()
        
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=1.0)

class AppState(Enum):
    STARTING = auto()
    INITIALIZING_NETWORK = auto()
    GETTING_PUBLIC_IP_FAILED = auto()
    IDLE = auto()
    CALL_INITIATING_REQUEST = auto()
    CALL_OUTGOING_WAITING_ACCEPTANCE = auto()
    CALL_INCOMING_RINGING = auto()
    IN_CALL = auto()
    CALL_TERMINATING_SELF_INITIATED = auto()
    CALL_REJECTING = auto()
    CALL_ENDED_LOCALLY_HUNG_UP = auto()
    CALL_ENDED_PEER_HUNG_UP = auto()
    CALL_ENDED_PEER_REJECTED = auto()
    CALL_ENDED_ERROR = auto()
    CALL_ENDED_REQUEST_FAILED = auto()
    CALL_ENDED_APP_CLOSING = auto()

class SignalType(Enum):
    HANGUP_SIGNAL = b"__VOICE_CHAT_HANGUP__"
    CALL_REQUEST_SIGNAL_PREFIX = b"__CALL_ME_PLEASE__:"
    CALL_ACCEPTED_SIGNAL = b"__CALL_ACCEPTED__"
    ACK_CALL_REQUEST_SIGNAL = b"__ACK_CALL_REQUEST__"
    ACK_HANGUP_SIGNAL = b"__ACK_HANGUP__"
    SPEAKER_STATUS_SIGNAL_PREFIX = b"__SPEAKER_STATUS__:"

class FeatureCodeManager:
    def __init__(self, key):
        self.key = key

    def _xor_string(self, s_bytes, key_bytes):
        key_len = len(key_bytes)
        return bytes([s_bytes[i] ^ key_bytes[i % key_len] for i in range(len(s_bytes))])

    def generate_feature_code(self, public_ip, public_port):
        if not public_ip or public_port is None:
            return None,
        try:
            plain_text = f"{public_ip}:{public_port}"
            key_bytes = self.key.encode('utf-8')
            xored_bytes = self._xor_string(plain_text.encode('utf-8'), key_bytes)
            feature_code = base64.urlsafe_b64encode(xored_bytes).decode('utf-8')
            return feature_code, None
        except Exception as e:
            return None, f"生成错误: {e}"

    def parse_feature_code(self, code_str):
        try:
            key_bytes = self.key.encode('utf-8')
            decoded_xored_bytes = base64.urlsafe_b64decode(code_str.encode('utf-8'))
            plain_text_bytes = self._xor_string(decoded_xored_bytes, key_bytes)
            plain_text = plain_text_bytes.decode('utf-8')

            if ':' not in plain_text:
                raise ValueError("解析出的文本不含':'分隔符")

            ip, port_str = plain_text.split(':', 1)
            port = int(port_str)
            socket.inet_aton(ip) # Validate IP
            if not (1 <= port <= 65535):
                raise ValueError("端口号超出范围 (1-65535)")
            return ip, port, None
        except ValueError as e:
            return None, None, f"内容无效: {e}"
        except (base64.binascii.Error, UnicodeDecodeError) as e:
            return None, None, f"格式错误: {e}"
        except (socket.error, OSError) as e:
             return None, None, f"IP地址无效: {e}"
        except Exception as e:
            return None, None, f"未知解析错误: {e}"

class AudioManager:
    def __init__(self, log_callback, deduplication_callback=None):
        self.log_callback = log_callback
        self.deduplication_callback = deduplication_callback
        self.p = None
        self.audio_stream_in = None
        self.audio_stream_out = None
        self.mic_muted = False
        self.played_audio_seq_nums = deque(maxlen=SEQ_NUM_DEQUE_MAXLEN)

    def initialize_pyaudio_core(self):
        if self.p is not None:
            self.log_callback("AudioManager: PyAudio core already initialized.", is_warning=True)
            return True
        try:
            self.p = pyaudio.PyAudio()
            self.log_callback("AudioManager: PyAudio core initialized successfully.")
            return True
        except Exception as e:
            self.log_callback(f"CRITICAL: PyAudio核心初始化失败: {e}", is_error=True)
            self.p = None
            return False

    def is_initialized(self):
        return self.p is not None

    @staticmethod
    def _decode_device_name(name_bytes):
        if not isinstance(name_bytes, bytes):
            return str(name_bytes)
        try:
            return name_bytes.decode(locale.getpreferredencoding(False), errors='replace')
        except (UnicodeDecodeError, LookupError):
            try:
                return name_bytes.decode(sys.getfilesystemencoding(), errors='replace')
            except (UnicodeDecodeError, LookupError):
                return name_bytes.decode('utf-8', errors='replace')

    def _safe_close_stream(self, stream_attr_name):
        stream = getattr(self, stream_attr_name, None)
        if stream:
            try:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
            except Exception as e:
                self.log_callback(f"关闭音频流 {stream_attr_name} 时出错: {e}")
            finally:
                setattr(self, stream_attr_name, None)
        return True

    def open_output_stream(self):
        if not self.p:
            self.log_callback("PyAudio未初始化，无法打开输出流。")
            return False
        if self.audio_stream_out and self.audio_stream_out.is_active():
             self._safe_close_stream('audio_stream_out')

        try:
            default_info = self.p.get_default_output_device_info()
            target_device_index = default_info['index']
            final_device_info = self.p.get_device_info_by_index(target_device_index)
            device_name_log = self._decode_device_name(final_device_info['name'])

            self.audio_stream_out = self.p.open(format=PYAUDIO_FORMAT,
                                                channels=PYAUDIO_CHANNELS,
                                                rate=PYAUDIO_RATE,
                                                output=True,
                                                frames_per_buffer=PYAUDIO_CHUNK,
                                                output_device_index=target_device_index)
            self.log_callback(f"输出音频流已打开: '{device_name_log}' (Index: {target_device_index})")
            return True
        except IOError as e:
             self.log_callback(f"打开输出音频流时发生IOError: {e}. 检查采样率/格式兼容性。", is_error=True)
             self.audio_stream_out = None
             return False
        except Exception as e:
            self.log_callback(f"打开输出音频流失败: {e}", is_error=True)
            self.audio_stream_out = None
            return False

    def open_input_stream(self):
        if not self.p:
            self.log_callback("PyAudio未初始化，无法打开输入流。")
            return False
        self._safe_close_stream('audio_stream_in')
        try:
            device_info = self.p.get_default_input_device_info()
            input_device_index = device_info['index']
            device_name = self._decode_device_name(device_info['name'])
            self.log_callback(f"尝试打开输入流: '{device_name}' (Index: {input_device_index})")

            self.audio_stream_in = self.p.open(format=PYAUDIO_FORMAT,
                                               channels=PYAUDIO_CHANNELS,
                                               rate=PYAUDIO_RATE,
                                               input=True,
                                               frames_per_buffer=PYAUDIO_CHUNK,
                                               input_device_index=input_device_index)
            self.log_callback("输入音频流已成功打开。")
            return True
        except IOError as e:
             self.log_callback(f"打开输入音频流时发生IOError: {e}. 检查采样率/格式兼容性。", is_error=True)
             self.audio_stream_in = None
             return False
        except Exception as e:
            self.log_callback(f"打开输入音频流失败: {e}", is_error=True)
            self.audio_stream_in = None
            return False

    def read_chunk_from_mic(self):
        if not self.p:
            self.log_callback("AudioManager: PyAudio (self.p) is None, cannot read mic.", is_error=True)
            return None
        if not self.audio_stream_in:
            self.log_callback("AudioManager: Input stream (self.audio_stream_in) is None, cannot read mic. Was open_input_stream successful?", is_warning=True)
            return None

        try:
            current_stream_obj_id = id(self.audio_stream_in) if self.audio_stream_in else "None"
            is_active = self.audio_stream_in.is_active() if self.audio_stream_in else False
            
            if is_active:
                return self.audio_stream_in.read(PYAUDIO_CHUNK, exception_on_overflow=False)
            else:
                self.log_callback(f"AudioManager: Input stream (ID: {current_stream_obj_id}) is not active. Returning None.", is_warning=True)
                return None

        except (IOError, OSError) as e:
            self.log_callback(f"AudioManager: IOError/OSError reading from microphone: {e}. Stream may be corrupted.", is_error=True)
            raise
        except Exception as e_generic:
            self.log_callback(f"AudioManager: A generic error occurred while reading from microphone: {e_generic}. Stream obj ID: {current_stream_obj_id}", is_error=True)
            traceback.print_exc()
            self._safe_close_stream('audio_stream_in')
            return None

    def write_chunk_to_speaker(self, audio_data, seq_num):
        if not audio_data:
            return False
        is_duplicate = seq_num in self.played_audio_seq_nums
        if is_duplicate:
            if self.deduplication_callback:
                self.deduplication_callback()
            return True
        else:
            self.played_audio_seq_nums.append(seq_num)
            if not self.audio_stream_out:
                self.log_callback("尝试写入扬声器但输出流未打开或已关闭。", is_warning=True)
                return False
            try:
                self.audio_stream_out.write(audio_data)
                return True
            except (IOError, OSError) as e:
                self.log_callback(f"写入输出流时错误 (IO/OS): {e}. 音频播放可能中断。", is_warning=True)
                return False
            except Exception as e_write:
                self.log_callback(f"写入输出流时发生未知错误: {e_write}", is_warning=True)
                return False

    def toggle_mic_mute(self):
        self.mic_muted = not self.mic_muted
        self.log_callback("麦克风已静音。" if self.mic_muted else "麦克风已取消静音。")
        return self.mic_muted

    def clear_played_sequence_numbers(self):
        self.played_audio_seq_nums.clear()

    def close_input_stream(self):
        self._safe_close_stream('audio_stream_in')

    def terminate(self):
        self._safe_close_stream('audio_stream_in')
        self._safe_close_stream('audio_stream_out')
        if self.p:
            try:
                self.p.terminate()
            except Exception as e:
                self.log_callback(f"PyAudio terminate error: {e}")
            self.p = None

class NetworkManager:
    def __init__(self, log_callback, data_received_callback):
        self.log_callback = log_callback
        self.data_received_callback = data_received_callback
        self.udp_socket = None
        self.is_listening = False
        self.receive_thread = None

        self.local_port = 0
        self.public_ip = None
        self.public_port = None

    def _find_available_random_port(self, host="0.0.0.0", start_range=49152, end_range=65535, max_tries=RANDOM_PORT_MAX_TRIES):
        for _ in range(max_tries):
            port = random.randint(start_range, end_range)
            try:
                temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                temp_sock.bind((host, port))
                temp_sock.close()
                return port
            except OSError:
                continue
        self.log_callback(f"在 {max_tries} 次尝试后未能找到可用随机端口。")
        return None

    def _stun_generate_transaction_id(self):
        return os.urandom(12)

    def _stun_create_request(self, transaction_id, include_change_request=False):
        msg_type = 0x0001  # Binding Request
        msg_length = 0
        
        attributes_payload = b''

        if include_change_request:
            change_request_type = 0x0003
            change_request_length = 4
            change_request_value = 0x00000006 # Change IP and Port
            attributes_payload += struct.pack("!HH L", change_request_type, change_request_length, change_request_value)
            msg_length += (4 + change_request_length) # type + length + value

        header = struct.pack("!HHL12s", msg_type, msg_length, 0x2112A442, transaction_id)
        return header + attributes_payload
    
    def check_nat_openness_for_unsolicited_responses(self, stun_host=DEFAULT_STUN_HOST, stun_port=DEFAULT_STUN_PORT):
        self.log_callback(f"STUN_TEST_OPENNESS: Testing NAT openness with CHANGE-REQUEST to {stun_host}:{stun_port}...")
        if self.udp_socket is None or self.udp_socket._closed:
            self.log_callback(f"STUN_TEST_OPENNESS: Main socket not initialized or closed. Test failed.", is_warning=True)
            return False

        original_timeout = None
        try:
            original_timeout = self.udp_socket.gettimeout()
            self.udp_socket.settimeout(1.0) # Shorter timeout for this test

            transaction_id = self._stun_generate_transaction_id()
            request_message = self._stun_create_request(transaction_id, include_change_request=True)

            self.udp_socket.sendto(request_message, (stun_host, stun_port))

            data, addr = self.udp_socket.recvfrom(1024)

            if addr[0] != stun_host: # Or check against resolved IP of stun_host
                self.log_callback(f"STUN_TEST_OPENNESS: Received response from unexpected IP {addr[0]} (expected {stun_host}). Assuming test passed as *a* response was received.", is_warning=True)
            
            if len(data) >= 20: # Basic check for STUN message
                msg_type_resp, _, magic_cookie_resp, transaction_id_resp = struct.unpack("!HHL12s", data[:20])
                if magic_cookie_resp == 0x2112A442 and transaction_id_resp == transaction_id:
                    self.log_callback(f"STUN_TEST_OPENNESS: Received valid STUN response (type 0x{msg_type_resp:04X}) from {addr}. NAT appears to allow response. Test PASSED.")
                    return True
                else:
                    self.log_callback(f"STUN_TEST_OPENNESS: Received data from {addr}, but not a valid STUN response matching transaction. Test FAILED.", is_warning=True)
                    return False
            else:
                self.log_callback(f"STUN_TEST_OPENNESS: Received short data packet from {addr}. Test FAILED.", is_warning=True)
                return False

        except socket.timeout:
            self.log_callback("STUN_TEST_OPENNESS: Request timed out. NAT might be restrictive. Test FAILED.", is_warning=True)
            return False
        except socket.gaierror as e:
            self.log_callback(f"STUN_TEST_OPENNESS: Failed to resolve STUN server {stun_host} ({e}). Test FAILED.", is_error=True)
            return False
        except OSError as e:
             self.log_callback(f"STUN_TEST_OPENNESS: Socket error (OSError): {e}. Test FAILED.", is_error=True)
             return False
        except Exception as e:
            self.log_callback(f"STUN_TEST_OPENNESS: Unknown exception: {e}. Test FAILED.", is_error=True)
            return False
        finally:
            if original_timeout is not None and self.udp_socket and not self.udp_socket._closed:
                try: self.udp_socket.settimeout(original_timeout)
                except: pass
        return False # Default fail

    def _stun_parse_response(self, data, sent_transaction_id):
        STUN_MAGIC_COOKIE = 0x2112A442
        if len(data) < 20:
            self.log_callback("STUN: 响应过短.")
            return None, None

        msg_type, msg_length, magic_cookie, transaction_id_resp = struct.unpack("!HHL12s", data[:20])

        if magic_cookie != STUN_MAGIC_COOKIE:
            self.log_callback("STUN: 响应magic cookie无效.")

        if transaction_id_resp != sent_transaction_id:
            self.log_callback("STUN: Transaction ID不匹配. (继续处理，某些服务器可能行为不同)")

        if msg_type == 0x0101: # Binding Success Response
            pass
        elif msg_type == 0x0111: # Binding Error Response
            self.log_callback("STUN: 服务器返回错误响应.")
            return None, None
        else:
            self.log_callback(f"STUN: 响应类型异常: 0x{msg_type:04X}")
            return None, None

        offset = 20
        parsed_public_ip, parsed_public_port = None, None

        while offset < len(data):
            if offset + 4 > len(data): break
            attr_type, attr_length = struct.unpack("!HH", data[offset:offset+4])
            offset += 4

            if offset + attr_length > len(data):
                self.log_callback("STUN: 属性长度超出响应数据。")
                break
            attr_value = data[offset:offset+attr_length]
            offset += attr_length

            padding = (4 - (attr_length % 4)) % 4
            offset += padding

            if attr_type == 0x0001: # MAPPED-ADDRESS
                if len(attr_value) >= 8 and attr_value[0] == 0x00 and attr_value[1] == 0x01:
                    port_val = struct.unpack("!H", attr_value[2:4])[0]
                    ip_val = socket.inet_ntoa(attr_value[4:8])
                    parsed_public_ip, parsed_public_port = ip_val, port_val
            elif attr_type == 0x0020: # XOR-MAPPED-ADDRESS
                if len(attr_value) >= 8 and attr_value[0] == 0x00 and attr_value[1] == 0x01:
                    xport_pack, xip_pack = attr_value[2:4], attr_value[4:8]
                    
                    pport = struct.unpack("!H", xport_pack)[0] ^ (STUN_MAGIC_COOKIE >> 16)
                    
                    pip_pack_int = struct.unpack("!L", xip_pack)[0] ^ STUN_MAGIC_COOKIE
                    pip_pack_bytes = struct.pack("!L", pip_pack_int)
                    pip = socket.inet_ntoa(pip_pack_bytes)
                    
                    parsed_public_ip, parsed_public_port = pip, pport

        if parsed_public_ip and parsed_public_port:
            return parsed_public_ip, parsed_public_port
        else:
            self.log_callback("STUN: 未从属性中解析出公网地址。")
            return None, None

    def get_public_address_with_stun(self, stun_host=DEFAULT_STUN_HOST, stun_port=DEFAULT_STUN_PORT):
        self.log_callback(f"尝试通过 STUN 服务器 {stun_host}:{stun_port} 获取公网地址...")
        if self.udp_socket is None or self.udp_socket._closed:
            self.log_callback(f"STUN: 主套接字未初始化或已关闭。无法执行STUN。")
            return None, None

        original_timeout = None
        try:
            original_timeout = self.udp_socket.gettimeout()
            self.udp_socket.settimeout(1.0)

            transaction_id = self._stun_generate_transaction_id()
            request_message = self._stun_create_request(transaction_id, include_change_request=False) 

            self.udp_socket.sendto(request_message, (stun_host, stun_port))
            data, addr = self.udp_socket.recvfrom(1024)

            if original_timeout is not None: self.udp_socket.settimeout(original_timeout)
            
            public_ip, public_port = self._stun_parse_response(data, transaction_id)

            if public_ip and public_port:
                self.log_callback(f"STUN 结果: 公网 IP={public_ip}, 公网 Port={public_port}")
                return public_ip, public_port
            else:
                self.log_callback("STUN: 未能解析出公网地址")
                return None, None

        except socket.timeout:
            self.log_callback("STUN 查询超时，无响应。")
        except socket.gaierror as e:
            self.log_callback(f"STUN 查询失败: 无法解析STUN服务器地址 {stun_host} ({e})")
        except OSError as e:
             self.log_callback(f"STUN 查询socket错误 (OSError): {e}")
        except Exception as e:
            self.log_callback(f"STUN 查询发生未知异常: {e}")
        finally:
            if original_timeout is not None and self.udp_socket and not self.udp_socket._closed:
                try: self.udp_socket.settimeout(original_timeout)
                except: pass
        return None, None

    def start_listening_and_stun(self):
        self.local_port = self._find_available_random_port()
        if self.local_port is None:
            self.log_callback("自动启动失败: 无法找到可用的随机本地端口。", is_error=True)
            return False, "启动失败: 无可用端口"

        self.log_callback(f"已自动选择本地监听端口: {self.local_port}")

        if self.udp_socket and not self.udp_socket._closed:
            try: self.udp_socket.close()
            except Exception as e_close: self.log_callback(f"关闭旧套接字时出错: {e_close}")
        self.udp_socket = None

        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(('0.0.0.0', self.local_port))
            self.udp_socket.settimeout(1.0)
        except OSError as e:
            self.log_callback(f"主套接字绑定本地端口 {self.local_port} 失败: {e}", is_error=True)
            self._cleanup_socket()
            return False, f"启动失败: 端口 {self.local_port} 绑定失败"

        self.log_callback("正在获取公网地址 (STUN)...")
        pub_ip, pub_port = self.get_public_address_with_stun()
        self.public_ip, self.public_port = pub_ip, pub_port

        if not (self.public_ip and self.public_port):
            self.log_callback("未能自动获取公网地址。可能仅限局域网通信。", is_warning=True)

        self.is_listening = True
        self.receive_thread = threading.Thread(target=self._receive_loop_target, daemon=True, name="ReceiveAudioThread")
        self.receive_thread.start()
        
        if self.public_ip and self.public_port:
            return True, None
        else:
            return True, "公网地址获取失败"

    def _receive_loop_target(self):
        self.log_callback("接收线程已启动。")
        while self.is_listening:
            if self.udp_socket is None or self.udp_socket._closed:
                if self.is_listening: # Only log if it was unexpected
                    self.log_callback("接收线程：UDP套接字已关闭或未初始化，线程终止。", is_warning=True)
                break
            try:
                data, addr = self.udp_socket.recvfrom(MAX_PACKET_SIZE)
                if not data: continue

                if self.data_received_callback:
                    try:
                        self.data_received_callback(data, addr)
                    except Exception as e_cb:
                        self.log_callback(f"处理接收数据的回调函数中发生错误: {e_cb}", is_error=True)
                        traceback.print_exc()


            except socket.timeout:
                continue
            except OSError as e:
                if self.is_listening:
                    self.log_callback(f"接收音频时发生socket.recvfrom错误 (OSError): {e}", is_error=True)
            except Exception as e:
                if self.is_listening:
                    self.log_callback(f"接收音频时发生未知错误: {e}", is_error=True)
                    traceback.print_exc()
        self.log_callback("接收线程已停止。")

    def send_packet(self, data, address):
        if self.udp_socket and not self.udp_socket._closed and address:
            try:
                self.udp_socket.sendto(data, address)
                return True
            except socket.error as e_sock_send:
                self.log_callback(f"发送数据包至 {address} 时发生socket错误: {e_sock_send}", is_warning=True)
            except Exception as e_send:
                self.log_callback(f"发送数据包至 {address} 时发生未知错误: {e_send}", is_warning=True)
        elif not self.udp_socket or self.udp_socket._closed:
            self.log_callback(f"尝试发送数据包但套接字已关闭或未初始化。", is_warning=True)
        elif not address:
            self.log_callback(f"尝试发送数据包但目标地址为空。", is_warning=True)
        return False
        
    def _cleanup_socket(self):
        if self.udp_socket:
            current_socket = self.udp_socket
            self.udp_socket = None
            if not current_socket._closed:
                try:
                    current_socket.close()
                except Exception as e:
                    self.log_callback(f"清理主UDP套接字时出错: {e}")

    def stop_listening(self):
        prev_is_listening = self.is_listening
        self.is_listening = False
        self._cleanup_socket()

        if self.receive_thread and self.receive_thread.is_alive():
            if prev_is_listening: # Only log if it was actually running
                self.log_callback("正在等待接收线程停止...")
            try:
                self.receive_thread.join(timeout=0.5) 
            except Exception as e_join:
                self.log_callback(f"接收线程join时出错: {e_join}")
            if self.receive_thread and self.receive_thread.is_alive():
                self.log_callback("接收线程join超时。", is_warning=True)
        self.receive_thread = None
        self.public_ip = None
        self.public_port = None

class UIManager:
    def __init__(self, master, app_callbacks, log_callback, app_instance): # Added app_instance
        global DEFAULT_FALLBACK_FONT
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
            DEFAULT_FALLBACK_FONT = DESIRED_FONT_FAMILY
            self.log_callback(f"已尝试注册/定位字体，将尝试使用字体家族: '{DEFAULT_FALLBACK_FONT}'.")
        else:
            self.log_callback(f"未成功注册/定位自定义字体，将使用回退字体: '{DEFAULT_FALLBACK_FONT}'.")

        if DEFAULT_FALLBACK_FONT == DESIRED_FONT_FAMILY:
            try:
                self.log_callback(f"尝试将 CustomTkinter 主题字体设置为: '{DEFAULT_FALLBACK_FONT}'")
                for widget_name in ThemeManager.theme:
                    if isinstance(ThemeManager.theme[widget_name], dict) and "font" in ThemeManager.theme[widget_name]:
                        original_font_tuple = ThemeManager.theme[widget_name]["font"]
                        if isinstance(original_font_tuple, (list, tuple)) and len(original_font_tuple) > 0:
                            new_font_list = list(original_font_tuple)
                            new_font_list[0] = DEFAULT_FALLBACK_FONT
                            ThemeManager.theme[widget_name]["font"] = tuple(new_font_list)
            except Exception as e_theme:
                self.log_callback(f"修改主题默认字体时出错: {e_theme}. CustomTkinter 将使用其默认字体或特定控件的备用字体.")
        
        self.log_callback(f"最终配置CTkFont时使用的字体家族: '{DEFAULT_FALLBACK_FONT}'")
        self.FONT_LABEL = ctk.CTkFont(family=DEFAULT_FALLBACK_FONT, size=FONT_SIZE_LABEL)
        self.FONT_TEXTBOX = ctk.CTkFont(family=DEFAULT_FALLBACK_FONT, size=FONT_SIZE_TEXTBOX)
        self.FONT_TITLE = ctk.CTkFont(family=DEFAULT_FALLBACK_FONT, size=FONT_SIZE_TITLE)
        self._setup_ui()

    def unload_custom_font(self):
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

        self.lbl_status = ctk.CTkLabel(status_indicator_display_frame, text="正在启动...", font=ctk.CTkFont(family=DEFAULT_FALLBACK_FONT, size=FONT_SIZE_STATUS), anchor="w")
        self.lbl_status.grid(row=0, column=0, sticky="w")

        self.multi_part_status_frame = ctk.CTkFrame(status_indicator_display_frame, fg_color="transparent")

        self.status_font = ctk.CTkFont(family=DEFAULT_FALLBACK_FONT, size=FONT_SIZE_STATUS)
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

        self.is_running_main_op = False # Will be set true after successful init
        self.send_thread = None
        self.send_sequence_number = 0

        self.indicator_blinker_timer = SingleThreadPreciseTimer(self.master, name="IndicatorBlinkerThread")
        self.call_request_ack_timer_id = None
        self.hangup_ack_timer_id = None
        self.final_idle_status_timer_id = None
        self.initialization_thread = None # For the new init thread

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
        status_msg = f"{STATUS_LOCALLY_HUNG_UP} ({peer_display_name})" # What UI will actually show via _transition_to_call_ended_state
        
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
        status_msg = f"已拒绝来自 {peer_display_name} 的呼叫" # What UI will actually show via _transition_to_call_ended_state
        
        can_call_again = self._is_peer_info_valid(self.ui_manager.get_peer_ip_entry(), self.ui_manager.get_peer_port_entry()) and \
                         self.audio_manager.is_initialized() and self.is_running_main_op
        return {
            "status_message": status_msg,
            "status_color": COLOR_STATUS_WARNING, # Rejection color
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
        status_message = _reason # Default base message
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
        
        if self.audio_manager.is_initialized() and self.network_manager.local_port: # i.e., basic network is up
            status_message = STATUS_WAITING_FOR_REMOTE_INFO # Trigger multipart display

        self._generate_and_update_feature_code()
        return {
            "status_message": status_message, # Pass the message, UIManager handles multipart
            "status_color": COLOR_STATUS_ERROR, # Base color, parts might differ
            "peer_entry_enabled": True, "parse_btn_enabled": True,
            "call_btn_state": call_btn_state,
            "local_ip_text": self.network_manager.public_ip or "获取失败",
            "local_port_text": str(self.network_manager.public_port or "N/A")
        }

    def _update_ui_for_idle_state(self, reason, peer_address_tuple, associated_data):
        status_message = STATUS_WAITING_FOR_REMOTE_INFO # This will be handled by UIManager
        status_color = COLOR_STATUS_INFO # Default, UIManager might override parts
        call_btn_state = "disabled"

        _ip = self.ui_manager.get_peer_ip_entry()
        _port = self.ui_manager.get_peer_port_entry()
        if self._is_peer_info_valid(_ip, _port):
            status_message = STATUS_READY_TO_CALL_OR_RECEIVE
            if self.audio_manager.is_initialized() and self.is_running_main_op:
                call_btn_state = "normal"
        
        self._generate_and_update_feature_code()
        return {
            "status_message": status_message, "status_color": status_color, # Pass the base message
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
            if not reason and peer_address_tuple: # Default message if reason is empty
                 status_message = f"{STATUS_LOCALLY_HUNG_UP} ({self._get_peer_display_name_for_ui(peer_address_tuple)})"
            elif not reason:
                 status_message = STATUS_LOCALLY_HUNG_UP
        elif self.app_state == AppState.CALL_ENDED_PEER_HUNG_UP:
            status_color = COLOR_STATUS_WARNING
        elif self.app_state == AppState.CALL_ENDED_PEER_REJECTED:
            status_color = COLOR_STATUS_WARNING
            if not reason and peer_address_tuple: # Default message
                status_message = f"已拒绝来自 {self.get_peer_display_name_for_ui(peer_address_tuple)} 的呼叫" # Or a more general rejection message
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
            self.hang_up_call(initiated_by_peer=False, error_occurred=False, reason="用户界面操作挂断")
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
                self._transition_to_call_ended_state(AppState.CALL_ENDED_ERROR, "内部错误 (接听时无对方地址)", None)
                return

            self.log_message(f"用户接听了来自 {self.peer_full_address} 的呼叫。")
            self._proceed_with_call_setup(is_accepting_call=True)
        else:
            self.log_message(f"接听按钮按下，但应用状态 ({self.app_state.name}) 不正确。忽略。", is_warning=True)

    def _ui_on_reject_call_clicked(self):
        if self.app_state == AppState.CALL_INCOMING_RINGING:
            if not self.peer_full_address:
                self.log_message("CRITICAL: 尝试拒绝但 peer_full_address 未设置。", is_error=True)
                self._transition_to_call_ended_state(AppState.CALL_ENDED_ERROR, "内部错误 (拒绝时无对方地址)", None)
                return
            
            self.log_message(f"用户拒绝了来自 {self.peer_full_address} 的呼叫。")
            self.hang_up_call(initiated_by_peer=False, error_occurred=False, 
                              reason=f"用户拒绝来自 {self.peer_full_address[0]} 的呼叫")
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
            if not is_accepting_call: # 我方呼叫，收到ACK后进入此路径
                if self.app_state in [AppState.CALL_OUTGOING_WAITING_ACCEPTANCE, AppState.IN_CALL]:
                    self.log_message(f"_proceed_with_call_setup (outgoing call) called while state is {self.app_state.name}. Potential repeat. Ignoring.", is_warning=True)
                    return
            else: # 对方呼叫，我方接听后进入此路径
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

            self.peer_wants_to_receive_audio = True # 通话开始时，默认对方是愿意接收音频的
            self.my_speaker_switch_is_on = True     # 通话开始时，默认我方扬声器开关是开启的

            if hasattr(self, 'ui_manager') and hasattr(self.ui_manager, 'switch_speaker_mute') and self.ui_manager.switch_speaker_mute.winfo_exists():
                current_switch_state_int = self.ui_manager.switch_speaker_mute.get() # 0 or 1
                
                if self.my_speaker_switch_is_on and current_switch_state_int == 0: # 内部是开，UI是关
                    self.ui_manager.switch_speaker_mute.select()
                    self.log_message("同步UI: 扬声器开关已从视觉关闭状态切换为开启状态以匹配内部状态。")
                elif not self.my_speaker_switch_is_on and current_switch_state_int == 1: # 内部是关，UI是开
                    self.ui_manager.switch_speaker_mute.deselect()
                    self.log_message("同步UI: 扬声器开关已从视觉开启状态切换为关闭状态以匹配内部状态。")

                self.ui_manager.update_mute_switch_text(self.audio_manager.mic_muted, not self.my_speaker_switch_is_on)
            else:
                self.log_message("警告: _proceed_with_call_setup 中无法访问 UI Manager 或扬声器开关。", is_warning=True)


            self.send_sequence_number = 0
            self.audio_manager.clear_played_sequence_numbers()

            if not self.audio_manager.open_input_stream():
                self.hang_up_call(initiated_by_peer=False, error_occurred=True, reason="麦克风打开失败")
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

    def hang_up_call(self, initiated_by_peer=False, error_occurred=False, reason="", is_app_closing=False):
        current_state_on_hangup_call = self.app_state
        self.log_message(f"hang_up_call: by_peer={initiated_by_peer}, error={error_occurred}, reason='{reason}', "
                         f"closing={is_app_closing}, current_state={current_state_on_hangup_call.name}")

        if self.call_request_ack_timer_id is not None:
            self.master.after_cancel(self.call_request_ack_timer_id)
            self.call_request_ack_timer_id = None
        self.indicator_blinker_timer.cancel()

        target_address_for_this_hangup = self._determine_hangup_target_address(current_state_on_hangup_call)

        if is_app_closing:
            if target_address_for_this_hangup and self._is_state_active_or_pending_call(current_state_on_hangup_call):
                self.log_message("App closing during active/pending call. Attempting one-time HANGUP signal.")
                self._cleanup_active_call_resources() 
                self.network_manager.send_packet(SignalType.HANGUP_SIGNAL.value, target_address_for_this_hangup)
            return

        if initiated_by_peer:
            peer_ip_display = target_address_for_this_hangup[0] if target_address_for_this_hangup else "对方"
            final_reason = reason if reason else f"{STATUS_PEER_HUNG_UP} ({peer_ip_display})"
            final_state = AppState.CALL_ENDED_PEER_HUNG_UP
            if STATUS_PEER_REJECTED in reason: 
                final_state = AppState.CALL_ENDED_PEER_REJECTED
            
            self._transition_to_call_ended_state(final_state, final_reason, target_address_for_this_hangup,
                                               cleanup_resources=True, cancel_active_hangup_retries=True)
            return

        if error_occurred:
            peer_ip_display = target_address_for_this_hangup[0] if target_address_for_this_hangup else "对方"
            final_reason = reason if reason else f"通话因错误终止 ({peer_ip_display})"
            final_state = AppState.CALL_ENDED_ERROR
            if "超时" in reason or "呼叫请求失败" in reason or "发送呼叫请求错误" in reason:
                 final_state = AppState.CALL_ENDED_REQUEST_FAILED
            
            self._transition_to_call_ended_state(final_state, final_reason, target_address_for_this_hangup,
                                               cleanup_resources=True, cancel_active_hangup_retries=True)
            return

        if not target_address_for_this_hangup:
            self.log_message("本地主动挂断/操作，但无明确通话对象或当前状态不涉及通话。清理并返回IDLE/Ended状态。", is_warning=True)
            final_reason = reason if reason else "操作取消/无通话对象"
            target_final_state = AppState.IDLE
            if current_state_on_hangup_call.name.startswith("CALL_ENDED_") and \
               current_state_on_hangup_call != AppState.CALL_ENDED_APP_CLOSING:
                target_final_state = current_state_on_hangup_call
            self._transition_to_call_ended_state(target_final_state, final_reason, None,
                                               cleanup_resources=True, cancel_active_hangup_retries=True)
            return

        if current_state_on_hangup_call in [
            AppState.IN_CALL, 
            AppState.CALL_OUTGOING_WAITING_ACCEPTANCE,
            AppState.CALL_INITIATING_REQUEST, 
            AppState.CALL_INCOMING_RINGING # This is when user rejects an incoming call
        ]:
            self.log_message(f"用户在状态 {current_state_on_hangup_call.name} 时主动操作结束通话/拒绝。播放挂断提示音。")
            self._play_notification_sound(SOUND_PEER_HANGUP)

        is_rejection_context = (current_state_on_hangup_call == AppState.CALL_INCOMING_RINGING)
        
        final_ui_reason_for_display = ""
        final_ui_target_state = AppState.IDLE 

        if is_rejection_context:
            final_ui_reason_for_display = f"已拒绝来自 {target_address_for_this_hangup[0]} 的呼叫"
            final_ui_target_state = AppState.CALL_ENDED_PEER_REJECTED 
        else: 
            final_ui_reason_for_display = f"{STATUS_LOCALLY_HUNG_UP} ({target_address_for_this_hangup[0]})"
            final_ui_target_state = AppState.CALL_ENDED_LOCALLY_HUNG_UP
        
        log_prefix_for_ack_wait = "已拒绝" if is_rejection_context else STATUS_LOCALLY_HUNG_UP
        self._send_hangup_and_begin_ack_wait(
            target_address=target_address_for_this_hangup,
            reason_for_log_and_ui_prefix=log_prefix_for_ack_wait, 
            is_rejection_context=is_rejection_context
        )

        self._transition_to_call_ended_state(
            final_ui_target_state,
            final_ui_reason_for_display,
            target_address_for_this_hangup,
            cleanup_resources=True, 
            cancel_active_hangup_retries=False 
        )

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
            self.log_message(f"呼叫请求至 {peer_addr_attempted[0]} 的ACK超时。")
            
            self._transition_to_call_ended_state(
                AppState.CALL_ENDED_REQUEST_FAILED,
                f"呼叫请求失败 ({peer_addr_attempted[0]}) - 无应答",
                peer_address_tuple=peer_addr_attempted,
                cleanup_resources=False 
            )
        else:
            self.log_message(f"呼叫请求ACK超时，但状态为 {self.app_state.name}。忽略。")

    def _handle_hangup_ack_timeout(self):
        self.hangup_ack_timer_id = None 

        if not self.current_hangup_target_address or self.app_state == AppState.CALL_ENDED_APP_CLOSING:
            self.log_message(f"挂断/拒绝ACK超时，但无重试目标 ({self.current_hangup_target_address}) 或应用关闭。停止静默重试。")
            if self.current_hangup_target_address: # Ensure cleared if somehow still set
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

                if self.final_idle_status_timer_id is None: # Check if timer has already run or was never relevant
                    self.log_message(f"挂断ACK已收到。之前的3秒转换IDLE定时器已过或不适用。"
                                     f"主动从 {self.app_state.name} 转换到 IDLE。")
                    self._simple_reset_call_vars_and_set_state(
                        "", # Reason determined by IDLE state handler
                        AppState.IDLE,
                        acked_peer_addr,
                        cancel_active_hangup_retries=True # Already done by clearing targets
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
        current_call_peer_addr = None

        if self.app_state in [
            AppState.CALL_INITIATING_REQUEST, AppState.CALL_OUTGOING_WAITING_ACCEPTANCE,
            AppState.IN_CALL, AppState.CALL_INCOMING_RINGING
        ]:
            current_call_peer_addr = self.peer_full_address if self.peer_full_address else self.peer_address_for_call_attempt
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
            self._play_notification_sound(SOUND_PEER_HANGUP)
            reason_for_hangup = f"{STATUS_PEER_HUNG_UP} ({addr[0]})"

            if self.app_state == AppState.CALL_OUTGOING_WAITING_ACCEPTANCE or \
               self.app_state == AppState.CALL_INITIATING_REQUEST:
                reason_for_hangup = f"{STATUS_PEER_REJECTED} ({addr[0]})" 
                self.log_message(f"对方 {addr} 拒绝/取消了呼叫 (状态: {self.app_state.name})。")
            elif self.app_state == AppState.IN_CALL:
                self.log_message(f"对方 {addr} 在通话中挂断。")
            elif self.app_state == AppState.CALL_INCOMING_RINGING:
                reason_for_hangup = f"对方 ({addr[0]}) 已取消呼叫"
                self.log_message(f"来电者 {addr} 在振铃期间挂断 (呼叫被取消)。")
            elif self.current_hangup_target_address and addr == self.current_hangup_target_address:
                 self.log_message(f"对方 {addr} 也发送了挂断信号，在我方后台尝试终止时。标记为对方挂断。")


            if self.master.winfo_exists():
                 self.master.after(0, self.hang_up_call, True, False, reason_for_hangup)
            else:
                 self.hang_up_call(True, False, reason_for_hangup)
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
                                self.master.after(0, self.hang_up_call, False, True, "麦克风连续读取错误")
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
                            self.master.after(0, self.hang_up_call, False, True, f"音频发送未知错误: {e_read_send}")
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

        is_call_context_active = self._is_state_active_or_pending_call(original_state_on_close) or \
                                 (self.current_hangup_target_address is not None)

        if is_call_context_active:
            self.log_message("应用程序关闭时通话/呼叫仍处于活动状态，发送最后的挂断信号。")
            self.hang_up_call(is_app_closing=True, reason="应用程序关闭")

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

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if __name__ == "__main__":
    try:
        locale.setlocale(locale.LC_ALL, '') 
    except locale.Error as e:
        print(f"Warning: Could not set system default locale: {e}. Using default 'C' locale.")

    root = ctk.CTk()
    icon_path = resource_path(APP_ICON_FILENAME)
    root.iconbitmap(icon_path)
    app = VoiceChatApp(root)
    root.mainloop()