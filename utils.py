import threading
import time
import base64
import socket
import sys
import os
import binascii

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
            args_to_run = ()

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
                        args_to_run = self._args if self._args is not None else ()

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
            socket.inet_aton(ip)
            if not (1 <= port <= 65535):
                raise ValueError("端口号超出范围 (1-65535)")
            return ip, port, None

        except (binascii.Error, UnicodeDecodeError) as e:
            return None, None, f"格式错误: {e}"
        except ValueError as e:
            return None, None, f"内容无效: {e}"
        except (socket.error, OSError) as e:
             return None, None, f"IP地址无效: {e}"
        except Exception as e:
            return None, None, f"未知解析错误: {e}"

def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)