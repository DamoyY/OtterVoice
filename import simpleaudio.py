import simpleaudio
import numpy as np
# 设定提示音参数
frequency = 440  # 频率为440Hz（A音）
duration = 1.0   # 持续1秒
sample_rate = 44100  # 采样率

# 生成时间点数组
t = np.linspace(0, duration, int(sample_rate * duration), False)

# 生成正弦波数据
note = np.sin(frequency * t * 2 * np.pi)

# 将数据缩放为16位PCM音频
audio = note * (2**15 - 1) / np.max(np.abs(note))
audio = audio.astype(np.int16)

# 播放音频数据
play_obj = simpleaudio.play_buffer(audio, 1, 2, sample_rate)
play_obj.wait_done()