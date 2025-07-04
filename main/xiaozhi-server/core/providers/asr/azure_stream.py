import os
import shutil
import time
import asyncio
from typing import Optional, Tuple, List
import opuslib_next
from core.providers.asr.base import ASRProviderBase
from config.logger import setup_logging
from core.providers.asr.dto.dto import InterfaceType

try:
    import azure.cognitiveservices.speech as speechsdk
except ImportError:
    print(
        """
    Importing the Speech SDK for Python failed.
    Refer to
    https://docs.microsoft.com/azure/cognitive-services/speech-service/quickstart-python for
    installation instructions.
    """
    )

TAG = __name__
logger = setup_logging()

MAX_RETRIES = 2
RETRY_DELAY = 1  # 重试延迟（秒）

class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.interface_type = InterfaceType.STREAM
        self.config = config
        self.text = ""
        self.decoder = opuslib_next.Decoder(16000, 1)
        self.is_processing = False
        self.server_ready = False  # 服务器准备状态
        self.delete_audio_file = delete_audio_file
        self.conn = None

        # 基础配置初始化
        self.key = config.get("key")
        self.region = config.get("region")
        self.speech_config = speechsdk.SpeechConfig(self.key, self.region)
        self.result_future = None

        # 语言配置
        self.auto_detect_language = config.get("auto_detect_language", False)
        self.languages = config.get("languages", ["zh-CN", "en-US", "ja-JP"])
        self.primary_language = config.get("primary_language", "zh-CN")

        # 设置语言配置
        if self.auto_detect_language:
            # 启用自动语言检测
            self._setup_auto_language_detection()
        else:
            # 使用单一语言
            self.speech_config.speech_recognition_language = self.primary_language

        self.audio_stream = speechsdk.audio.PushAudioInputStream()
        self.audio_config = speechsdk.audio.AudioConfig(stream=self.audio_stream)

        self.recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config,
            audio_config=self.audio_config,
        )

    def _setup_auto_language_detection(self):
        """设置自动语言检测"""
        try:
            # 创建自动语言检测配置
            auto_detect_source_language_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                languages=self.languages
            )

            # 设置语音配置以使用自动语言检测
            self.speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "1000"
            )

            # 创建支持自动语言检测的识别器
            self.recognizer = speechsdk.SpeechRecognizer(
                speech_config=self.speech_config,
                audio_config=self.audio_config,
                auto_detect_source_language_config=auto_detect_source_language_config
            )

            logger.bind(tag=TAG).info(f"已启用自动语言检测，支持语言: {', '.join(self.languages)}")

        except Exception as e:
            logger.bind(tag=TAG).error(f"设置自动语言检测失败: {str(e)}")
            # 回退到单一语言模式
            self.speech_config.speech_recognition_language = self.primary_language
            logger.bind(tag=TAG).info(f"回退到单一语言模式: {self.primary_language}")

    async def open_audio_channels(self, conn):
        await super().open_audio_channels(conn)

    async def receive_audio(self, conn, audio, audio_have_voice):
        conn.asr_audio.append(audio)
        conn.asr_audio = conn.asr_audio[-10:]

        if audio_have_voice and not self.is_processing:
            try:
                await self._start_recognition(conn)
            except Exception as e:
                logger.bind(tag=TAG).error(f"开始识别失败: {str(e)}")
                await self._cleanup()
                return

        if self.is_processing:
            try:
                pcm_frame = self.decoder.decode(audio, 960)
                self.audio_stream.write(pcm_frame)
            except Exception as e:
                logger.bind(tag=TAG).warning(f"发送音频失败: {str(e)}")
                await self._cleanup()

    async def _start_recognition(self, conn):
        self.conn = conn
        # 设置回调函数
        self.recognizer.recognized.connect(self._on_recognized)
        self.recognizer.recognizing.connect(self._on_recognizing)
        self.recognizer.canceled.connect(self._on_canceled)
        self.recognizer.session_started.connect(self._on_session_started)
        self.recognizer.session_stopped.connect(self._on_session_stopped)

        self.is_processing = True
        self.server_ready = False  # 重置服务器准备状态

        # 开始连续识别
        self.result_future = self.recognizer.start_continuous_recognition_async()
        logger.bind(tag=TAG).info("已发送开始请求，等待服务器准备...")

    def _on_recognized(self, evt):
        """识别完成回调"""
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:

            self.text = evt.result.text

            logger.bind(tag=TAG).info(f"识别结果1: {evt.result.text}")

            # TODO:需要处理此处异步识别传值到self.text

            self.conn.reset_vad_states()

        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            logger.bind(tag=TAG).info("无法识别语音")

        asyncio.create_task(self.handle_voice_stop(self.conn, None))

    def _on_recognizing(self, evt):
        """正在识别回调"""
        detected_language = "未知"
        if self.auto_detect_language and hasattr(evt.result, 'language'):
            detected_language = evt.result.language

        logger.bind(tag=TAG).debug(f"正在识别 [{detected_language}]: {evt.result.text}")

    def _on_canceled(self, evt):
        """识别取消回调"""
        cancellation_details = evt.result.cancellation_details
        logger.bind(tag=TAG).error(f"识别取消: {cancellation_details.reason}")

        self.is_processing = False
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            logger.bind(tag=TAG).error(f"错误详情: {cancellation_details.error_details}")

    def _on_session_started(self, evt):
        """会话开始回调"""
        logger.bind(tag=TAG).info("语音识别会话已开始")

    def _on_session_stopped(self, evt):
        """会话结束回调"""
        logger.bind(tag=TAG).info("语音识别会话已结束")
        self.is_processing = False

    async def _cleanup(self):
        """清理资源"""
        self.is_processing = False
        self.server_ready = False  # 重置服务器准备状态

        try:
            self.recognizer.stop_continuous_recognition()
            self.audio_stream.close()
        except Exception as e:
            logger.bind(tag=TAG).error(f"清理资源失败: {str(e)}")

    async def speech_to_text(
            self, opus_data: List[bytes], session_id: str, audio_format="opus"
    ) -> Tuple[Optional[str], Optional[str]]:
        """获取识别结果"""
        result = self.text
        self.text = ""
        return result, None

    async def close(self):
        """关闭资源"""
        await self._cleanup()
