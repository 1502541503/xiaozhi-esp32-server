import asyncio
import time
from typing import Optional
import azure.cognitiveservices.speech as speechsdk
from core.providers.asr.base import ASRProviderBase
from config.logger import setup_logging
from core.providers.asr.dto.dto import InterfaceType
import gzip
import opuslib_next
import threading

from core.utils.util import _parse_accept_language

TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.last_audio_time = None
        self.interface_type = InterfaceType.STREAM
        self.config = config
        self.delete_audio_file = delete_audio_file
        self.is_processing = False
        self._voice_stop_handled = False
        self.conn = None

        # Azure配置参数
        self.api_key = config.get("api_key")
        self.region = config.get("region")

        # 初始化SpeechConfig
        self.speech_config = speechsdk.SpeechConfig(self.api_key, self.region)

        # 音频流配置
        self.stream_format = speechsdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
        self.push_stream = speechsdk.audio.PushAudioInputStream(stream_format=self.stream_format)
        self.audio_config = speechsdk.audio.AudioConfig(stream=self.push_stream)

        # 识别器相关
        self.recognizer: Optional[speechsdk.SpeechRecognizer] = None
        self.recognition_task = None
        self.result_text = ""
        self.session_started = False
        self.decoder = opuslib_next.Decoder(16000, 1)

        # 用于在不同线程中调度asyncio任务
        self.loop = asyncio.get_event_loop()

        self.supports_langs = [
            'af-ZA', 'am-ET', 'ar-AE', 'as-IN', 'az-AZ', 'bg-BG', 'bn-IN', 'bs-BA',
            'ca-ES', 'cs-CZ', 'cy-GB', 'da-DK', 'de-AT', 'el-GR', 'en-AU', 'es-AR',
            'et-EE', 'eu-ES', 'fa-IR', 'fi-FI', 'il-PH', 'fr-BE', 'ga-IE', 'gl-ES',
            'gu-IN', 'he-IL', 'hi-IN', 'hr-HR', 'hu-HU', 'hy-AM', 'id-ID', 'is-IS',
            'it-CH', 'ja-JP', 'jv-ID', 'ka-GE', 'kk-KZ', 'km-KH', 'kn-IN', 'ko-KR',
            'lo-LA', 'lt-LT', 'lv-LV', 'mk-MK', 'ml-IN', 'mn-MN', 'mr-IN', 'ms-MY',
            'mt-MT', 'my-MM', 'nb-NO', 'ne-NP', 'nl-BE', 'or-IN', 'pa-IN', 'pl-PL',
            'ps-AF', 'pt-BR', 'ro-RO', 'ru-RU', 'si-LK', 'sk-SK', 'sl-SI', 'so-SO',
            'sq-AL', 'sr-RS', 'sv-SE', 'sw-KE', 'ta-IN', 'te-IN', 'th-TH', 'tr-TR',
            'uk-UA', 'ur-IN', 'uz-UZ', 'vi-VN', 'uu-CN', 'ue-CN', 'zh-CN', 'zu-ZA'
        ]

    def find_first_matching_lang(self, lang_code):
        logger.bind(tag=TAG).info(f"获取客户端源语言: {lang_code}")
        lang_code = _parse_accept_language(lang_code)
        logger.bind(tag=TAG).info(f"转换客户端后目标语言: {lang_code}")

        for code in self.supports_langs:
            if code.startswith(lang_code + '-'):
                return code
        return 'zh-CN'

    async def open_audio_channels(self, conn):
        await super().open_audio_channels(conn)
        self.conn = conn

    async def receive_audio(self, conn, audio, audio_have_voice):

        conn.asr_audio.append(audio)
        conn.asr_audio = conn.asr_audio[-10:]
        if audio_have_voice:
            self.last_audio_time = time.time()

        # 如果是第一次有声音且未开始处理，则初始化识别器
        if audio_have_voice and not self.is_processing:
            try:
                self.is_processing = True
                await self._start_recognition(conn)
            except Exception as e:
                logger.bind(tag=TAG).error(f"启动Azure流式识别失败: {str(e)}")
                self.is_processing = False
                return

        # 发送音频数据到流
        if self.is_processing and self.push_stream:
            try:
                pcm_frame = self.decoder.decode(audio, 960)
                self.push_stream.write(bytes(pcm_frame))
            except Exception as e:
                logger.bind(tag=TAG).info(f"发送音频数据时发生错误: {e}")

    async def _start_recognition(self, conn):
        """启动Azure流式语音识别"""
        try:
            target_lang = self.find_first_matching_lang(conn.language)
            logger.bind(tag=TAG).info(f"最终识别语言: {target_lang}")
            # 创建识别器
            self.recognizer = speechsdk.SpeechRecognizer(
                speech_config=self.speech_config,
                audio_config=self.audio_config,
                language=target_lang
            )

            # 注册事件处理函数
            self.recognizer.recognizing.connect(self._on_recognizing)
            self.recognizer.recognized.connect(self._on_recognized)
            self.recognizer.session_started.connect(self._on_session_started)
            self.recognizer.session_stopped.connect(self._on_session_stopped)
            self.recognizer.canceled.connect(self._on_canceled)

            # 启动识别
            self.result_text = ""
            self.session_started = False

            # 在后台线程中启动连续识别
            await asyncio.get_event_loop().run_in_executor(None, self.recognizer.start_continuous_recognition)

            logger.bind(tag=TAG).info("Azure流式语音识别已启动")

        except Exception as e:
            logger.bind(tag=TAG).error(f"启动Azure流式识别时出错: {str(e)}")
            raise

    def _on_recognized(self, evt: speechsdk.SpeechRecognitionEventArgs):
        """处理最终识别结果"""
        result = evt.result
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            if result.text:
                self.result_text = result.text
                logger.bind(tag=TAG).info(f"最终识别结果: {result.text}")
                # 通知语音结束并处理结果
                if self.conn:
                    logger.bind(tag=TAG).info("开始执行打断方法。。。")
                    # 使用线程安全的方式调度异步任务
                    self._schedule_async_task(self._handle_voice_stop())
        elif result.reason == speechsdk.ResultReason.NoMatch:
            logger.bind(tag=TAG).info("未识别到语音内容")
            # 即使没有识别到内容，也可能需要处理语音结束
            if self.conn:
                logger.bind(tag=TAG).info("未识别到内容，但仍需处理语音结束")
                self._schedule_async_task(self._handle_voice_stop())
        else:
            logger.bind(tag=TAG).info(f"识别状态: {result.reason}")

    def _schedule_async_task(self, coro):
        """在线程安全的方式下调度异步任务"""

        def schedule():
            asyncio.run_coroutine_threadsafe(coro, self.loop)

        # 在新的线程中调度任务，避免阻塞Azure SDK回调
        thread = threading.Thread(target=schedule, daemon=True)
        thread.start()

    def _on_recognizing(self, evt: speechsdk.SpeechRecognitionEventArgs):
        """处理中间识别结果"""
        result = evt.result
        if result.text:
            logger.bind(tag=TAG).debug(f"中间识别结果: {result.text}")

    def _on_session_started(self, evt: speechsdk.SessionEventArgs):
        """会话开始事件"""
        self.session_started = True
        logger.bind(tag=TAG).info("Azure语音识别会话已开始")

    def _on_session_stopped(self, evt: speechsdk.SessionEventArgs):
        """会话停止事件"""
        self.is_processing = False
        logger.bind(tag=TAG).info("Azure语音识别会话已停止")

    def _on_canceled(self, evt: speechsdk.SpeechRecognitionCanceledEventArgs):
        """识别取消事件"""
        cancellation_details = evt.cancellation_details
        logger.bind(tag=TAG).error(f"识别被取消: {cancellation_details.reason}")
        logger.bind(tag=TAG).error(f"错误详情: {cancellation_details.error_details}")
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            logger.bind(tag=TAG).error(f"错误详情: {cancellation_details.error_details}")
        self.is_processing = False

    async def _handle_voice_stop(self):

        """处理语音结束"""
        # if self._voice_stop_handled:
        #     logger.bind(tag=TAG).info("handle_voice_stop 已处理，跳过重复调用")
        #     return

        self._voice_stop_handled = True

        # 停止连续识别
        if self.recognizer:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.recognizer.stop_continuous_recognition)

        # 处理识别结果
        if self.conn:
            self.conn.reset_vad_states()
            await self.handle_voice_stop(self.conn, None)

        self.is_processing = False

    async def speech_to_text(self, opus_data, session_id, audio_format):
        """获取识别结果"""
        result = self.result_text
        self.result_text = ""  # 清空结果
        return result, None

    async def close(self):
        """关闭资源"""
        try:
            # 停止识别
            if self.recognizer:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.recognizer.stop_continuous_recognition)

            # 关闭音频流
            if self.push_stream:
                self.push_stream.close()

        except Exception as e:
            logger.bind(tag=TAG).error(f"关闭Azure ASR资源时出错: {str(e)}")
        finally:
            self.recognizer = None
            self.push_stream = None
            self.is_processing = False

    async def _cleanup(self):
        """清理资源"""
        logger.bind(tag=TAG).info("清理Azure ASR资源")
        self._voice_stop_handled = False
        self.is_processing = False
        self.result_text = ""
        await self.close()

    def stop_ws_connection(self):
        """停止连接（兼容接口）"""
        asyncio.create_task(self._handle_voice_stop())

    async def safe_handle_voice_stop(self, conn, arg):
        """安全处理语音结束"""
        if self._voice_stop_handled:
            logger.bind(tag=TAG).info("handle_voice_stop 已处理，跳过重复调用")
            return
        self._voice_stop_handled = True
        await self._handle_voice_stop()

    def generate_audio_default_header(self):
        return self.generate_header(
            version=0x01,
            message_type=0x02,
            message_type_specific_flags=0x00,
            serial_method=0x01,
            compression_type=0x01,
        )

    def generate_header(
            self,
            version=0x01,
            message_type=0x01,
            message_type_specific_flags=0x00,
            serial_method=0x01,
            compression_type=0x01,
            reserved_data=0x00,
            extension_header: bytes = b"",
    ):
        header = bytearray()
        header_size = int(len(extension_header) / 4) + 1
        header.append((version << 4) | header_size)
        header.append((message_type << 4) | message_type_specific_flags)
        header.append((serial_method << 4) | compression_type)
        header.append(reserved_data)
        header.extend(extension_header)
        return header
