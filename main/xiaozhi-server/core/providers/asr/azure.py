import asyncio
from typing import List
from core.providers.asr.base import ASRProviderBase
from config.logger import setup_logging

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
        self.config = config
        self.delete_audio_file = delete_audio_file

        # 基础配置初始化
        self.key = config.get("key")
        self.region = config.get("region")
        self.speech_config = speechsdk.SpeechConfig(self.key, self.region)
        self.result_future = None

        # 语言配置
        # TODO:需要适配多语言自动检测识别
        self.auto_detect_source_language_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
            languages=["zh-CN", "en-US", "ja-JP"]
        )

        self.stream_format = speechsdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
        self.push_stream = speechsdk.audio.PushAudioInputStream(stream_format=self.stream_format)
        self.audio_config = speechsdk.audio.AudioConfig(stream=self.push_stream)
        self.recognizer = speechsdk.SpeechRecognizer(speech_config=self.speech_config,
                                                     audio_config=self.audio_config,
                                                     auto_detect_source_language_config=self.auto_detect_source_language_config)

    async def speech_to_text(self, opus_data: List[bytes], session_id: str, audio_format="opus") -> tuple[
                                                                                                        str, None] | None:
        """语音转文本主处理逻辑"""
        file_path = None
        retry_count = 0

        while retry_count < MAX_RETRIES:
            try:
                # 1. 解码为 PCM
                if audio_format == "pcm":
                    pcm_data = opus_data
                else:
                    pcm_data = self.decode_opus(opus_data)
                combined_pcm_data = b"".join(pcm_data)

                self.push_stream.write(combined_pcm_data)
                self.push_stream.close()  # 重要，通知SDK音频已写完

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, self.recognizer.recognize_once)

                if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    return result.text, None
                else:
                    return "", None
            except Exception as e:
                logger.bind(tag=TAG).error(f"语音识别失败: {e}", exc_info=True)
                return "", file_path
        return None
