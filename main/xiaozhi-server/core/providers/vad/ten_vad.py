import numpy as np
import time

from config.logger import setup_logging
from core.providers.vad.base import VADProviderBase
import opuslib_next

TAG = __name__
logger = setup_logging()


class VADProvider(VADProviderBase):
    def __init__(self, config):

        logger.bind(tag=TAG).info("Initializing VADProvider", config)

        # 配置参数
        self.speech_threshold = config.get('speech_threshold', 0.5)
        self.silence_threshold = config.get('silence_threshold', 0.5)
        # TEN VAD需要帧长度与hop_size一致
        self.frame_length = config.get('frame_length', 256)
        self.sample_rate = config.get('sample_rate', 16000)
        self.min_speech_duration = config.get('min_speech_duration', 200)  # ms
        self.max_silence_duration = config.get('max_silence_duration', 800)  # ms

        # TEN VAD特定参数
        self.hop_size = 256  # 16 ms per frame (默认值与官方demo一致)

        # 状态变量
        self.is_speaking = False
        self.speech_start_time = 0
        self.last_speech_time = 0
        self.consecutive_speech_frames = 0
        self.consecutive_silence_frames = 0

        # 加载TEN VAD库
        self._load_vad_library()

        # 初始化VAD
        self.vad = self._create_vad_instance()

        self.decoder = opuslib_next.Decoder(16000, 1)

    def _load_vad_library(self):
        """加载TEN VAD共享库"""
        try:
            # 尝试导入ten_vad模块
            from ten_vad import TenVad
            self.TenVad = TenVad
            logger.bind(tag=TAG).info("Successfully imported TenVad")
        except ImportError:
            logger.bind(tag=TAG).error(
                """
                    导入失败，请安装环境: 
                    1.pip install -U git+https://github.com/TEN-framework/ten-vad.git"
                    2.sudo apt update
                    3.sudo apt install libc++1
                """)
            raise

    def _create_vad_instance(self):
        """创建VAD实例"""
        try:
            # 根据官方demo，初始化需要传入hop_size和threshold
            vad = self.TenVad(self.hop_size, self.speech_threshold)
            logger.bind(tag=TAG).info(
                f"TenVAD instance created successfully with hop_size={self.hop_size}, threshold={self.speech_threshold}")
            return vad
        except Exception as e:
            logger.bind(tag=TAG).error(f"Failed to create TenVAD instance: {str(e)}")
            raise

    def is_vad(self, conn, data):
        """检测音频数据中的语音活动
        Args:
            conn: 连接对象
            data: 音频数据(Opus格式)
        Returns:
            bool: 是否检测到语音活动
        """
        try:
            # 解码Opus音频数据为PCM
            pcm_data = self.decoder.decode(data, 960)

            # 如果解码失败，返回False
            if pcm_data is None or len(pcm_data) == 0:
                return False

            # 将bytes数据转换为numpy数组 (保持int16类型)
            pcm_array = np.frombuffer(pcm_data, dtype=np.int16)

            # 处理PCM数据，分帧进行VAD检测
            current_time = time.time() * 1000  # Convert seconds to milliseconds
            frames = self._split_into_frames(pcm_array)

            for frame in frames:
                # 确保帧大小符合TEN VAD要求的256
                if len(frame) > self.hop_size:
                    frame = frame[:self.hop_size]
                elif len(frame) < self.hop_size:
                    frame = np.pad(frame, (0, self.hop_size - len(frame)), 'constant', constant_values=0)

                # 保持int16类型
                frame_int16 = frame.astype(np.int16)

                # 使用TEN VAD进行检测
                # 根据官方demo，使用process方法并获取两个返回值
                try:
                    out_probability, out_flag = self.vad.process(frame_int16)
                    # out_flag为1表示检测到语音，0表示非语音
                    is_speech_frame = out_flag == 1
                    logger.bind(tag=TAG).debug(f"VAD result: probability={out_probability}, flag={out_flag}")
                except Exception as e:
                    logger.bind(tag=TAG).error(f"Error calling TenVAD process method: {str(e)}")
                    is_speech_frame = False

                # 更新语音状态
                if is_speech_frame:
                    self.consecutive_speech_frames += 1
                    self.consecutive_silence_frames = 0
                    self.last_speech_time = current_time

                    # 检测到连续的语音帧，开始语音
                    if self.consecutive_speech_frames >= 2 and not self.is_speaking:
                        self.is_speaking = True
                        self.speech_start_time = current_time
                        logger.bind(tag=TAG).debug(f"Speech started at {current_time}")
                else:
                    self.consecutive_silence_frames += 1
                    self.consecutive_speech_frames = 0

                    # 检测到足够长的静音，结束语音
                    if self.is_speaking and self.consecutive_silence_frames >= 5:
                        silence_duration = current_time - self.last_speech_time
                        if silence_duration >= self.max_silence_duration:
                            self.is_speaking = False
                            speech_duration = self.last_speech_time - self.speech_start_time
                            if speech_duration >= self.min_speech_duration:
                                logger.bind(tag=TAG).debug(f"Speech ended at {current_time}, duration: {speech_duration}ms")
                                return True
                            else:
                                logger.bind(tag=TAG).debug(
                                    f"Speech too short: {speech_duration}ms < {self.min_speech_duration}ms")

                # 如果正在说话，返回True
                return self.is_speaking

        except Exception as e:
            logger.bind(tag=TAG).error(f"VAD detection error: {str(e)}")
            return False


    def _split_into_frames(self, pcm_data):
        """将PCM数据分割成帧
        Args:
            pcm_data: PCM音频数据
        Returns:
            list: 帧列表
        """
        frames = []
        for i in range(0, len(pcm_data), self.frame_length):
            frame = pcm_data[i:i + self.frame_length]
            frames.append(frame)
        return frames


    def close(self):
        """关闭VAD资源"""
        logger.bind(tag=TAG).info("Closing TenVADProvider")
        # TEN VAD不需要显式关闭资源
        pass
