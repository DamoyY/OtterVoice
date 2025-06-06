# Otter Voice



**Otter Voice** is a simple, serverless, peer-to-peer (P2P) voice chat application built with Python. It allows two users to connect and talk directly over the internet without relying on a central server. The connection is established by exchanging a simple, one-time "Feature Code".

The application is written in Chinese (Simplified) and is designed for ease of use.

## Features

-   **Serverless P2P Connection**: No central server means your conversations are direct and private.
-   **Easy Connection via Feature Codes**: No need to manually find and type IP addresses. Just copy a single code to connect.
-   **STUN for NAT Traversal**: Automatically discovers your public IP address and port to enable connections even when you are behind a NAT router.
-   **NAT Openness Check**: Tests if your network configuration can reliably receive incoming calls.
-   **Basic Packet Loss/Duplication Handling**: Sends audio packets twice and uses a sequence number system to handle duplicates, improving audio stability on less reliable networks.
-   **Clean and Modern UI**: Built with `customtkinter` for a pleasant user experience.
-   **Real-time Mute Controls**: Mute your microphone or speaker at any time.
-   **Developer Mode**: An optional mode that displays detailed network information and logging for debugging.

## How It Works

Otter Voice establishes a direct UDP connection between two peers using the following process:

1.  **Initialization**: When the application starts, it binds to a random local UDP port.
2.  **STUN Discovery**: It contacts a public STUN (Session Traversal Utilities for NAT) server to discover its own public-facing IP address and port.
3.  **Feature Code Generation**: This public IP and port are then obfuscated (using a simple XOR cipher and Base64 encoding) into a single, shareable "Feature Code" (一次性特征码).
4.  **Connection Exchange**:
    -   **User A** copies their Feature Code and sends it to **User B** through any external means (e.g., instant messenger).
    -   **User B** pastes the code into their Otter Voice client. The application decodes it to get User A's public address.
5.  **Call Handshake**:
    -   User B clicks "Call" (呼叫), sending a call request signal directly to User A's address.
    -   User A's client receives the request and shows an incoming call notification.
    -   If User A clicks "Accept" (接听), a confirmation signal is sent back to User B.
6.  **Voice Stream**: The call is established. Both clients begin streaming microphone audio data directly to each other over UDP.

## Requirements

-   **Operating System**: **Windows only**. (Uses `winsound` for notifications and `ctypes` with `gdi32.dll` for custom font loading).
-   **Python**: Python 3.8+
-   **Python Libraries**:
    -   `customtkinter`
    -   `pyaudio`

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/otter-voice.git
    cd otter-voice
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    .\venv\Scripts\activate  # On Windows
    ```

3.  **Install the required libraries:**
    ```bash
    pip install customtkinter pyaudio
    ```

4.  **Custom Font (思源黑体):**
    The application is designed to use the "Source Han Sans" font for the best visual experience. The font file (`SourceHanSansSC-Regular.otf`) is included in this repository. The application will attempt to load it automatically on startup. If it fails, it will fall back to a system default font.

5.  **Run the application:**
    ```bash
    python OtterVoice.py
    ```

## How to Use

#### User A (Initiating the share)

1.  Run `OtterVoice.py`.
2.  The application will initialize and display your "One-time Feature Code" (一次性特征码) in the "本机" (Local) section.
3.  Click on the code to automatically copy it to your clipboard.
4.  Send this code to User B.

#### User B (Initiating the call)

1.  Run `OtterVoice.py`.
2.  Receive the Feature Code from User A.
3.  Click the "Paste One-time Feature Code" (粘贴一次性特征码) button. This will automatically parse the code and fill in the remote IP and Port fields.
4.  Click the "Call" (呼叫) button.

#### Establishing the Call

1.  User A will see an incoming call notification with "Accept" (接听) and "Reject" (拒绝) buttons.
2.  User A clicks "Accept" (接听).
3.  The call is now connected!

To end the call, either user can click the "Hang up" (挂断) button.

## Technical Details

-   **Protocol**: All communication, including signaling (call requests, acks, hangups) and audio data, occurs over UDP. Control signals are simple predefined byte strings.
-   **Audio Format**: Audio is captured and streamed as 16-bit signed integers at a 40,000 Hz sample rate in mono.
-   **Security**: The Feature Code is obfuscated with a simple XOR cipher. **This is not cryptographically secure** and is only intended to prevent casual snooping of IP addresses. Do not use this application for sensitive communications.
-   **Network Limitations**: The use of STUN helps with many common NAT types, but it may fail to establish a connection if one or both users are behind a Symmetric NAT or a particularly restrictive corporate firewall.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
