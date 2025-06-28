import socket
import threading
import random
import os
import struct
import traceback
from config import *
from typing import Callable, Optional, Tuple

class NetworkManager:
    def __init__(self, log_callback, data_received_callback: Optional[Callable[[bytes, Tuple[str, int]], None]] = None):
        self.log_callback = log_callback
        self.data_received_callback: Optional[Callable[[bytes, Tuple[str, int]], None]] = data_received_callback
        self.udp_socket = None
        self.is_listening = False
        self.receive_thread = None

        self.local_port = 0
        self.public_ip = None
        self.public_port = None
        self.is_cone_nat: Optional[bool] = None

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
        msg_type = 0x0001
        msg_length = 0
        
        attributes_payload = b''

        if include_change_request:
            change_request_type = 0x0003
            change_request_length = 4
            change_request_value = 0x00000006
            attributes_payload += struct.pack("!HH L", change_request_type, change_request_length, change_request_value)
            msg_length += (4 + change_request_length)

        header = struct.pack("!HHL12s", msg_type, msg_length, 0x2112A442, transaction_id)
        return header + attributes_payload
    
    def check_nat_openness_for_unsolicited_responses(self, stun_host=DEFAULT_STUN_HOST, stun_port=DEFAULT_STUN_PORT):
        self.log_callback(f"STUN_TEST_OPENNESS: Testing NAT openness with CHANGE-REQUEST to {stun_host}:{stun_port}...")
        if self.udp_socket is None or self.udp_socket.fileno() == -1:
            self.log_callback(f"STUN_TEST_OPENNESS: Main socket not initialized or closed. Test failed.", is_warning=True)
            return False

        original_timeout = None
        try:
            original_timeout = self.udp_socket.gettimeout()
            self.udp_socket.settimeout(2.0)

            transaction_id = self._stun_generate_transaction_id()
            request_message = self._stun_create_request(transaction_id, include_change_request=True)

            self.udp_socket.sendto(request_message, (stun_host, stun_port))
            data, addr = self.udp_socket.recvfrom(1024)

            self.log_callback(f"STUN_TEST_OPENNESS: Received a response from {addr}. NAT appears to be a Cone type. Test PASSED.")
            return True

        except socket.timeout:
            self.log_callback("STUN_TEST_OPENNESS: Request timed out. NAT is likely Symmetric. Test FAILED.", is_warning=True)
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
            if original_timeout is not None and self.udp_socket and self.udp_socket.fileno() != -1:
                try: self.udp_socket.settimeout(original_timeout)
                except: pass

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

        if msg_type == 0x0101: # Success response
            pass
        elif msg_type == 0x0111: # Error response
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
        if self.udp_socket is None or self.udp_socket.fileno() == -1:
            self.log_callback(f"STUN: 主套接字未初始化或已关闭。无法执行STUN。")
            return None, None

        original_timeout = None
        try:
            original_timeout = self.udp_socket.gettimeout()
            self.udp_socket.settimeout(2.0)

            transaction_id = self._stun_generate_transaction_id()
            request_message = self._stun_create_request(transaction_id, include_change_request=False) 

            self.udp_socket.sendto(request_message, (stun_host, stun_port))
            data, addr = self.udp_socket.recvfrom(1024)
            
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
            if original_timeout is not None and self.udp_socket and self.udp_socket.fileno() != -1:
                try: self.udp_socket.settimeout(original_timeout)
                except: pass
        return None, None

    def start_listening_and_stun(self):
        self.local_port = self._find_available_random_port()
        if self.local_port is None:
            self.log_callback("自动启动失败: 无法找到可用的随机本地端口。", is_error=True)
            return False, "启动失败: 无可用端口"

        self.log_callback(f"已自动选择本地监听端口: {self.local_port}")

        if self.udp_socket and self.udp_socket.fileno() != -1:
            try: self.udp_socket.close()
            except Exception as e_close: self.log_callback(f"关闭旧套接字时出错: {e_close}")
        self.udp_socket = None

        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(('0.0.0.0', self.local_port))
        except OSError as e:
            self.log_callback(f"主套接字绑定本地端口 {self.local_port} 失败: {e}", is_error=True)
            self._cleanup_socket()
            return False, f"启动失败: 端口 {self.local_port} 绑定失败"

        self.log_callback("正在获取公网地址 (STUN)...")

        stun_result = self.get_public_address_with_stun()
        if stun_result and len(stun_result) == 2:
            self.public_ip, self.public_port = stun_result
        else:
            self.public_ip, self.public_port = None, None

        if self.public_ip and self.public_port:
            self.log_callback("获取到公网地址，现在测试NAT类型...")
            self.is_cone_nat = self.check_nat_openness_for_unsolicited_responses()
            if self.is_cone_nat:
                self.log_callback("NAT类型测试结果：Cone NAT (良好)，应可接收来电。")
            else:
                self.log_callback("NAT类型测试结果：Symmetric NAT 或 防火墙限制 (较差)，可能无法接收来电。", is_warning=True)
        else:
            self.log_callback("未能自动获取公网地址。可能仅限局域网通信。", is_warning=True)
            self.is_cone_nat = False

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
            if self.udp_socket is None or self.udp_socket.fileno() == -1:
                if self.is_listening:
                    self.log_callback("接收线程：UDP套接字已关闭或未初始化，线程终止。", is_warning=True)
                break
            try:
                self.udp_socket.settimeout(1.0)
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
        if self.udp_socket and self.udp_socket.fileno() != -1 and address:
            try:
                self.udp_socket.sendto(data, address)
                return True
            except socket.error as e_sock_send:
                self.log_callback(f"发送数据包至 {address} 时发生socket错误: {e_sock_send}", is_warning=True)
            except Exception as e_send:
                self.log_callback(f"发送数据包至 {address} 时发生未知错误: {e_send}", is_warning=True)
        elif not self.udp_socket or self.udp_socket.fileno() == -1:
            self.log_callback(f"尝试发送数据包但套接字已关闭或未初始化。", is_warning=True)
        elif not address:
            self.log_callback(f"尝试发送数据包但目标地址为空。", is_warning=True)
        return False
        
    def _cleanup_socket(self):
        if self.udp_socket:
            current_socket = self.udp_socket
            self.udp_socket = None
            if current_socket.fileno() != -1:
                try:
                    current_socket.close()
                except Exception as e:
                    self.log_callback(f"清理主UDP套接字时出错: {e}")

    def stop_listening(self):
        prev_is_listening = self.is_listening
        self.is_listening = False
        self._cleanup_socket()

        if self.receive_thread and self.receive_thread.is_alive():
            if prev_is_listening:
                self.log_callback("正在等待接收线程停止...")
            try:
                self.receive_thread.join(timeout=1.5)
            except Exception as e_join:
                self.log_callback(f"接收线程join时出错: {e_join}")
            if self.receive_thread and self.receive_thread.is_alive():
                self.log_callback("接收线程join超时。", is_warning=True)
        self.receive_thread = None
        self.public_ip = None
        self.public_port = None
        self.is_cone_nat = None