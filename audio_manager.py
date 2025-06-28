import pyaudio
import locale
import sys
import traceback
from collections import deque
from config import *

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
            target_device_index = int(default_info['index'])
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
            input_device_index = int(device_info['index'])
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

        current_stream_obj_id = "unknown"
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

    def close_output_stream(self):
        self._safe_close_stream('audio_stream_out')

    def terminate(self):
        self._safe_close_stream('audio_stream_in')
        self._safe_close_stream('audio_stream_out')
        if self.p:
            try:
                self.p.terminate()
            except Exception as e:
                self.log_callback(f"PyAudio terminate error: {e}")
            self.p = None