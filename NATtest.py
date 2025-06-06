import socket
import struct
import random
import os
import time

# STUN 消息类型 (整数值)
STUN_MSG_BINDING_REQUEST = 0x0001
STUN_MSG_BINDING_RESPONSE = 0x0101
STUN_MSG_BINDING_ERROR_RESPONSE = 0x0111

# STUN 属性类型 (整数值)
STUN_ATTR_MAPPED_ADDRESS = 0x0001
STUN_ATTR_XOR_MAPPED_ADDRESS = 0x0020
STUN_ATTR_CHANGE_REQUEST = 0x0003
STUN_ATTR_SOURCE_ADDRESS = 0x0004
STUN_ATTR_CHANGED_ADDRESS = 0x0005
STUN_ATTR_ERROR_CODE = 0x0009
STUN_ATTR_SOFTWARE = 0x8022
STUN_ATTR_ALTERNATE_SERVER = 0x8023

STUN_MAGIC_COOKIE = b'\x21\x12\xA4\x42'
STUN_MAGIC_COOKIE_INT = 0x2112A442

STUN_SERVERS_CONFIG = [
    ("stun.miwifi.com", 3478),
    ("stun.chat.bilibili.com", 3478),
    ("stun.cloudflare.com", 3478),
]
STUN_SERVERS = []

def get_local_ip(target_host="8.8.8.8", target_port=80):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.0)
    try:
        s.connect((target_host, target_port))
        ip = s.getsockname()[0]
    except socket.gaierror:
        ip = "127.0.0.1"
    except OSError:
        ip = "127.0.0.1"
    except socket.timeout:
        ip = "127.0.0.1"
        print(f"Warning: get_local_ip timed out connecting to {target_host}:{target_port}")
    finally:
        s.close()
    return ip

def generate_transaction_id():
    return os.urandom(12)

def build_stun_request(transaction_id, change_ip=False, change_port=False):
    message_type_bytes = struct.pack('>H', STUN_MSG_BINDING_REQUEST)
    attributes = b''

    if change_ip or change_port:
        change_request_value = 0
        if change_ip:
            change_request_value |= 0x04
        if change_port:
            change_request_value |= 0x02
        
        attributes += struct.pack('>H', STUN_ATTR_CHANGE_REQUEST) # Type
        attributes += b'\x00\x04' # Length
        attributes += struct.pack('>I', change_request_value) # Value

    message_length = len(attributes)
    
    header = message_type_bytes + struct.pack('>H', message_length) + STUN_MAGIC_COOKIE + transaction_id
    return header + attributes

def parse_stun_address_attribute(attr_value, magic_cookie_int, is_xor=False):
    if len(attr_value) < 8:
        print(f"    [AddrParser] Address attribute value too short: {len(attr_value)} bytes, expected at least 8.")
        return None, None

    family = attr_value[1]
    if family != 0x01:
        print(f"    [AddrParser] Unsupported address family: {family}")
        return None, None

    port_bytes = attr_value[2:4]
    ip_bytes = attr_value[4:8]

    if is_xor:
        xor_port_val = struct.unpack('>H', port_bytes)[0]
        real_port = xor_port_val ^ (magic_cookie_int >> 16)
        
        xor_ip_val = struct.unpack('>I', ip_bytes)[0]
        real_ip_val = xor_ip_val ^ magic_cookie_int
        try:
            real_ip = socket.inet_ntoa(struct.pack('>I', real_ip_val))
        except OSError:
            print(f"    [AddrParser] XORed IP value {real_ip_val:08x} resulted in invalid IP.")
            return None, None
    else:
        real_port = struct.unpack('>H', port_bytes)[0]
        try:
            real_ip = socket.inet_ntoa(ip_bytes)
        except OSError:
            print(f"    [AddrParser] IP bytes {ip_bytes.hex()} resulted in invalid IP.")
            return None, None
            
    return real_ip, real_port

def parse_stun_response(data, expected_transaction_id):
    print(f"  [Parser] Parsing response (len={len(data)} bytes): {data.hex()[:80]}...")

    if len(data) < 20:
        print("  [Parser] Response too short for STUN header.")
        return None 

    msg_type_int, msg_length, magic_cookie_raw, transaction_id_raw = struct.unpack('>HH4s12s', data[:20])
    
    print(f"  [Parser] Msg Type (integer value): {msg_type_int} (0x{msg_type_int:04X})") # CORRECTED
    print(f"  [Parser] Msg Length: {msg_length} (payload is {msg_length} bytes, total packet received {len(data)})")
    print(f"  [Parser] Magic Cookie Raw: {magic_cookie_raw.hex()}, Expected: {STUN_MAGIC_COOKIE.hex()}")
    print(f"  [Parser] Transaction ID Raw: {transaction_id_raw.hex()}, Expected: {expected_transaction_id.hex()}")

    if magic_cookie_raw != STUN_MAGIC_COOKIE:
        print("  [Parser] Invalid magic cookie.")
        # return None # Be less strict for now, some old servers might behave differently

    if transaction_id_raw != expected_transaction_id:
        print("  [Parser] Transaction ID mismatch.")
        return None

    if msg_type_int == STUN_MSG_BINDING_ERROR_RESPONSE: # CORRECTED COMPARISON
        print("  [Parser] Received STUN Binding Error Response.")
        parsed_error = {"error": "STUN Binding Error", "code": "Unknown", "reason": "N/A"}
        offset = 20
        while offset < (20 + msg_length) and offset < len(data):
            if offset + 4 > len(data): break
            attr_type_int, attr_length = struct.unpack('>HH', data[offset:offset+4]) # attr_type_int is integer
            attr_value_offset = offset + 4
            if attr_value_offset + attr_length > len(data): break
            attr_value = data[attr_value_offset : attr_value_offset + attr_length]

            if attr_type_int == STUN_ATTR_ERROR_CODE: # CORRECTED COMPARISON
                if len(attr_value) >= 4:
                    error_class = attr_value[2] 
                    error_number = attr_value[3]
                    parsed_error["code"] = f"{error_class}{error_number:02d}"
                    error_reason_len = attr_length - 4
                    if error_reason_len > 0:
                        try:
                            parsed_error["reason"] = attr_value[4 : 4 + error_reason_len].decode('utf-8', errors='ignore')
                        except Exception:
                            parsed_error["reason"] = attr_value[4 : 4 + error_reason_len].hex()
                    print(f"  [Parser] STUN Error Code: {parsed_error['code']} - {parsed_error['reason']}")
                else:
                     print(f"  [Parser] ATTR_ERROR_CODE attribute too short: {len(attr_value)}")
                break 
            
            offset += (4 + attr_length)
            if attr_length % 4 != 0: offset += (4 - (attr_length % 4))
        return parsed_error

    if msg_type_int != STUN_MSG_BINDING_RESPONSE: # CORRECTED COMPARISON
        print(f"  [Parser] Not a Binding Response or recognized Error Response (Type: 0x{msg_type_int:04X}).")
        return None

    attributes_data_end = 20 + msg_length
    if attributes_data_end > len(data):
        print(f"  [Parser] Warning: Declared message length ({msg_length}) + header (20) "
              f"exceeds received packet size ({len(data)}). Truncating attribute parsing.")
        attributes_data_end = len(data)
    
    attributes_data = data[20:attributes_data_end]
    
    parsed_attrs = {
        "mapped_address": None, "source_address": None, "changed_address": None,
        "alternate_server": None, "software": None
    }

    offset = 0
    while offset < len(attributes_data):
        if offset + 4 > len(attributes_data):
            print(f"  [Parser] Attribute data too short at offset {offset} for type/length.")
            break
        attr_type_int, attr_length = struct.unpack('>HH', attributes_data[offset:offset+4]) # attr_type_int is integer
        attr_value_offset = offset + 4
        
        if attr_value_offset + attr_length > len(attributes_data):
            print(f"  [Parser] Attribute value extends beyond attribute data buffer. Attr Type 0x{attr_type_int:04X}, Declared Length {attr_length}")
            break
        
        attr_value = attributes_data[attr_value_offset : attr_value_offset + attr_length]
        print(f"  [Parser] Attr Type: 0x{attr_type_int:04X}, Length: {attr_length}, Value (hex): {attr_value.hex()[:40]}...") # CORRECTED

        ip, port = None, None
        if attr_type_int == STUN_ATTR_MAPPED_ADDRESS: # CORRECTED COMPARISON
            ip, port = parse_stun_address_attribute(attr_value, STUN_MAGIC_COOKIE_INT, transaction_id_raw, is_xor=False)
            if ip: parsed_attrs["mapped_address"] = (ip, port)
            print(f"    [Parser] Parsed MAPPED_ADDRESS: {ip}:{port}")
        elif attr_type_int == STUN_ATTR_XOR_MAPPED_ADDRESS: # CORRECTED COMPARISON
            ip, port = parse_stun_address_attribute(attr_value, STUN_MAGIC_COOKIE_INT, transaction_id_raw, is_xor=True)
            if ip: parsed_attrs["mapped_address"] = (ip, port)
            print(f"    [Parser] Parsed XOR_MAPPED_ADDRESS: {ip}:{port}")
        elif attr_type_int == STUN_ATTR_SOURCE_ADDRESS: # CORRECTED COMPARISON
            ip, port = parse_stun_address_attribute(attr_value, STUN_MAGIC_COOKIE_INT, transaction_id_raw, is_xor=False)
            if ip: parsed_attrs["source_address"] = (ip, port)
            print(f"    [Parser] Parsed SOURCE_ADDRESS: {ip}:{port}")
        elif attr_type_int == STUN_ATTR_CHANGED_ADDRESS: # CORRECTED COMPARISON
            ip, port = parse_stun_address_attribute(attr_value, STUN_MAGIC_COOKIE_INT, transaction_id_raw, is_xor=False)
            if ip: parsed_attrs["changed_address"] = (ip, port)
            print(f"    [Parser] Parsed CHANGED_ADDRESS (RFC3489): {ip}:{port}")
        elif attr_type_int == STUN_ATTR_ALTERNATE_SERVER: # CORRECTED COMPARISON
            ip, port = parse_stun_address_attribute(attr_value, STUN_MAGIC_COOKIE_INT, transaction_id_raw, is_xor=False)
            if ip: parsed_attrs["alternate_server"] = (ip, port)
            print(f"    [Parser] Parsed ALTERNATE_SERVER (RFC5389): {ip}:{port}")
        elif attr_type_int == STUN_ATTR_SOFTWARE: # CORRECTED COMPARISON
            try:
                software_name = attr_value.decode('utf-8', errors='ignore')
                parsed_attrs["software"] = software_name
                print(f"    [Parser] Parsed SOFTWARE: {software_name}")
            except Exception:
                 print(f"    [Parser] Error decoding SOFTWARE attribute: {attr_value.hex()}")
        
        current_attr_total_len = 4 + attr_length
        offset += current_attr_total_len
        if current_attr_total_len % 4 != 0:
            padding = 4 - (current_attr_total_len % 4)
            offset += padding
            
    print(f"  [Parser] Final parsed attributes: {parsed_attrs}")
    if parsed_attrs["alternate_server"] and not parsed_attrs["changed_address"]:
        parsed_attrs["changed_address"] = parsed_attrs["alternate_server"]
        
    return parsed_attrs

def send_stun_request_and_receive(sock, server_host, server_port, transaction_id, 
                                  change_ip=False, change_port=False, timeout=2.0):
    request_packet = build_stun_request(transaction_id, change_ip, change_port)
    
    print(f"  Sending STUN request to {server_host}:{server_port} (TID: {transaction_id.hex()[:8]}...)")
    
    try:
        sock.sendto(request_packet, (server_host, server_port))
        sock.settimeout(timeout)
        response_data, server_addr_tuple = sock.recvfrom(1024)
        print(f"  Received response from {server_addr_tuple} (len={len(response_data)})")
        return response_data, server_addr_tuple
    except socket.timeout:
        print(f"  Timeout waiting for response from {server_host}:{server_port}")
        return None, None
    except socket.gaierror:
        print(f"  Error resolving hostname {server_host} (gaierror)")
        return None, None
    except OSError as e:
        print(f"  OSError sending/receiving STUN to {server_host}:{server_port}: {e}")
        return None, None
    except Exception as e:
        print(f"  Unexpected error sending/receiving STUN to {server_host}:{server_port}: {e}")
        return None, None

def get_nat_type():
    global STUN_SERVERS
    if not STUN_SERVERS:
        print("错误：没有可用的 STUN 服务器。")
        return "无法确定 (无可用 STUN 服务器)"
        
    stun_server1_host, stun_server1_port = STUN_SERVERS[0]
    stun_server2_host, stun_server2_port = (STUN_SERVERS[1] if len(STUN_SERVERS) > 1 else (None, None))

    print(f"使用主 STUN 服务器: {stun_server1_host}:{stun_server1_port}")
    if stun_server2_host:
        print(f"使用次 STUN 服务器: {stun_server2_host}:{stun_server2_port}")
    else:
        print("警告: 只有一个可用 STUN 服务器，对称 NAT 检测可能依赖 CHANGED_ADDRESS。")

    default_local_ip = get_local_ip(stun_server1_host, stun_server1_port) 
    print(f"检测到的本地出站 IP (估算): {default_local_ip}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print("\n--- Test I: 基本 NAT 检测 ---")
    tid1 = generate_transaction_id()
    response_data_t1, server_addr_t1 = send_stun_request_and_receive(sock, stun_server1_host, stun_server1_port, tid1)

    if not response_data_t1:
        sock.close()
        return "UDP 被阻止 (Test I: 无法连接到 STUN 服务器或超时)"

    attrs_t1 = parse_stun_response(response_data_t1, tid1)
    
    if not attrs_t1:
        sock.close()
        return "STUN Test I 失败 (无法解析响应)"
    if attrs_t1.get("error"):
        sock.close()
        return f"STUN Test I 失败 (服务器错误: {attrs_t1.get('code', '')} {attrs_t1.get('reason', '')})"
    if not attrs_t1.get("mapped_address"):
        sock.close()
        return "STUN Test I 失败 (响应中未找到 MAPPED_ADDRESS 或 XOR_MAPPED_ADDRESS)"

    mapped_ip1, mapped_port1 = attrs_t1["mapped_address"]
    changed_addr_s1 = attrs_t1.get("changed_address")

    print(f"  Test I: 从 {server_addr_t1[0]}:{server_addr_t1[1]} 收到响应")
    print(f"  Test I: MAPPED-ADDRESS (Public IP:Port): {mapped_ip1}:{mapped_port1}")
    if attrs_t1.get("software"):
        print(f"  Test I: STUN Server Software: {attrs_t1['software']}")
    if changed_addr_s1:
        print(f"  Test I: Server's Alternate/Changed Address: {changed_addr_s1[0]}:{changed_addr_s1[1]}")
    else:
        print("  Test I: Server's Alternate/Changed Address: 未提供")
        
    if mapped_ip1 == default_local_ip:
        is_open_internet_candidate = True
        print(f"  Test I: MAPPED-ADDRESS ({mapped_ip1}) 与估算的本地出站 IP ({default_local_ip}) 相同。")
    else:
        is_open_internet_candidate = False
        print(f"  Test I: MAPPED-ADDRESS ({mapped_ip1}) 与估算的本地出站 IP ({default_local_ip}) 不同。可能在 NAT后。")

    print("\n--- Test II: 完全锥形 NAT 检测 ---")
    tid2 = generate_transaction_id()
    response_data_t2, server_addr_t2 = send_stun_request_and_receive(sock, stun_server1_host, stun_server1_port, tid2, 
                                                                    change_ip=True, change_port=True)
    
    if response_data_t2:
        attrs_t2 = parse_stun_response(response_data_t2, tid2)
        if attrs_t2 and not attrs_t2.get("error") and attrs_t2.get("mapped_address"):
            print(f"  Test II: 从 {server_addr_t2} (STUN 服务器的备用 IP/端口) 收到有效响应。")
            sock.close()
            return "完全锥形 NAT (Full Cone NAT)"
        elif attrs_t2 and attrs_t2.get("error"):
             print(f"  Test II: 从备用地址收到 STUN 错误响应: {attrs_t2.get('code')} {attrs_t2.get('reason')}. Full Cone test inconclusive.")
        elif attrs_t2:
            print(f"  Test II: 从 {server_addr_t2} 收到响应，但无MAPPED_ADDRESS或解析问题。Full Cone test inconclusive.")
        else:
            print(f"  Test II: 从 {server_addr_t2} 收到无法解析的响应。Full Cone test inconclusive.")
    else:
        print("  Test II: 未从 STUN 服务器的备用 IP/端口收到响应。不是完全锥形 NAT。")

    if is_open_internet_candidate:
        print(f"  Test I MAPPED-ADDRESS ({mapped_ip1}) 与本地 IP ({default_local_ip}) 相同，但 Test II 失败。")
        sock.close()
        is_private_ip = any(default_local_ip.startswith(prefix) for prefix in 
                            ("10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", 
                             "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.",
                             "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", "192.168."))
        if not is_private_ip:
            return "开放互联网 (Open Internet) 或 对称 UDP 防火墙"
        else:
            return "NAT 类型异常 (映射IP与私有本地IP相同，且 Full Cone 测试失败)"

    print("\n--- 对称 NAT 检测 ---")
    target_sym_host, target_sym_port = None, None
    if stun_server2_host and stun_server2_host != stun_server1_host:
        target_sym_host, target_sym_port = stun_server2_host, stun_server2_port
        print(f"  使用次 STUN 服务器 ({target_sym_host}:{target_sym_port}) 进行对称检测。")
    elif changed_addr_s1 and changed_addr_s1[0] != stun_server1_host:
        target_sym_host, target_sym_port = changed_addr_s1
        print(f"  使用主服务器的 Alternate/Changed Address ({target_sym_host}:{target_sym_port}) 进行对称检测。")
    else:
        print("  无合适的次 STUN 服务器或主服务器的 Alternate/Changed Address IP 不同于主服务器IP。对称 NAT 检测可能不确定。")

    mapped_ip2, mapped_port2 = None, None
    if target_sym_host and target_sym_port:
        tid3 = generate_transaction_id()
        response_data_t3, server_addr_t3 = send_stun_request_and_receive(sock, target_sym_host, target_sym_port, tid3)

        if response_data_t3:
            attrs_t3 = parse_stun_response(response_data_t3, tid3)
            if attrs_t3 and not attrs_t3.get("error") and attrs_t3.get("mapped_address"):
                mapped_ip2, mapped_port2 = attrs_t3["mapped_address"]
                print(f"  对称检测: 连接到 {target_sym_host}:{target_sym_port} 后，MAPPED-ADDRESS 为: {mapped_ip2}:{mapped_port2}")
                if (mapped_ip1, mapped_port1) != (mapped_ip2, mapped_port2):
                    print(f"  对称检测: Mapped address changed from ({mapped_ip1}:{mapped_port1}) to ({mapped_ip2}:{mapped_port2}).")
                    sock.close()
                    return "对称 NAT (Symmetric NAT)"
                else:
                    print(f"  对称检测: 到不同服务器的映射 ({mapped_ip2}:{mapped_port2}) 与 Test I ({mapped_ip1}:{mapped_port1}) 相同。")
            else:
                print(f"  对称检测: 从 {target_sym_host} 获取 MAPPED_ADDRESS 失败: {attrs_t3}. 对称 NAT 检测不确定。")
        else:
            print(f"  对称检测: 连接 {target_sym_host} 失败。对称 NAT 检测不确定。")
    
    print("\n--- 限制锥形 NAT 检测 ---")
    tid4 = generate_transaction_id()
    response_data_t4, server_addr_t4 = send_stun_request_and_receive(sock, stun_server1_host, stun_server1_port, tid4,
                                                                    change_ip=False, change_port=True)
    if response_data_t4:
        attrs_t4 = parse_stun_response(response_data_t4, tid4)
        if attrs_t4 and not attrs_t4.get("error") and attrs_t4.get("mapped_address"):
            print(f"  限制锥形检测: 从 {server_addr_t4} (STUN 服务器的相同 IP 但可能不同端口) 收到有效响应。")
            sock.close()
            return "限制锥形 NAT (Restricted Cone NAT)"
        else:
            print(f"  限制锥形检测: 收到响应但解析失败、错误或无MAPPED_ADDRESS: {attrs_t4}. 响应来源: {server_addr_t4}")
    else:
        print("  限制锥形检测: 未从 STUN 服务器的相同 IP 但不同端口收到响应。")

    sock.close()
    return "端口限制锥形 NAT (Port Restricted Cone NAT)"


if __name__ == "__main__":
    print("开始 NAT 类型检测 (这可能需要几秒钟)...")
    
    print("正在检查并解析 STUN 服务器...")
    temp_validated_servers = []
    resolved_ips = set()

    for host, port in STUN_SERVERS_CONFIG:
        if len(temp_validated_servers) >= 2 and len(resolved_ips) >=2 :
            break
        
        print(f"  正在尝试解析: {host}:{port}...")
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM, 0, socket.AI_ADDRCONFIG)
            if infos: 
                actual_host_ip = infos[0][4][0]
                if actual_host_ip not in resolved_ips:
                    temp_validated_servers.append((actual_host_ip, port))
                    resolved_ips.add(actual_host_ip)
                    print(f"  {host}:{port} (resolved to {actual_host_ip}) 添加到可用列表。")
                else:
                    print(f"  {host}:{port} (resolved to {actual_host_ip}) 已存在于解析列表，跳过。")
            else:
                print(f"  无法解析 STUN 服务器: {host}:{port} (getaddrinfo returned empty/filtered)")
        except socket.gaierror:
            print(f"  无法解析 STUN 服务器: {host}:{port} (gaierror)")
        except Exception as e:
            print(f"  检查 {host}:{port} 时发生未知错误: {e}")
            
    STUN_SERVERS = temp_validated_servers

    if not STUN_SERVERS:
        print("\n错误：没有可用的 STUN 服务器。请检查网络连接或 STUN_SERVERS_CONFIG 列表。")
    elif len(STUN_SERVERS) == 1:
        print("\n警告：只有一个可用的 STUN 服务器。对称 NAT 检测将依赖主服务器的 Alternate/Changed Address，可能不完全准确。")
        nat_type = get_nat_type()
        print(f"\n检测到的 NAT 类型: {nat_type}")
    else:
        nat_type = get_nat_type()
        print(f"\n检测到的 NAT 类型: {nat_type}")

    print("\n注意：")
    print("1. 此结果基于与公共 STUN 服务器的交互及 RFC 3489/5780 定义的测试流程。")
    print("2. 网络防火墙或运营商级 NAT (CGNAT) 可能影响结果。")
    print("3. “UDP 被阻止”通常意味着防火墙阻止出站 UDP 或 STUN 服务器不可达/超时。")