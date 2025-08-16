import asyncio
from typing import List
from core.providers.asr.base import ASRProviderBase
from config.logger import setup_logging
from core.utils.util import _parse_accept_language
from core.providers.asr.dto.dto import InterfaceType

import azure.cognitiveservices.speech as speechsdk

TAG = __name__
logger = setup_logging()

MAX_RETRIES = 2
RETRY_DELAY = 1  # 重试延迟（秒）


class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.config = config
        self.delete_audio_file = delete_audio_file
        self.interface_type = InterfaceType.NON_STREAM
        self.headers = None

        # 基础配置初始化
        self.api_key = config.get("api_key")
        self.region = config.get("region")

        self.speech_config = speechsdk.SpeechConfig(self.api_key, self.region)
        self.result_future = None

        self.stream_format = speechsdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
        self.push_stream = speechsdk.audio.PushAudioInputStream(stream_format=self.stream_format)
        self.audio_config = speechsdk.audio.AudioConfig(stream=self.push_stream)
        self.recognizer = None

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

    def init_headers(self, headers):
        self.headers = headers
        language = self.headers.get("accept-language", "zh")
        if self.recognizer is None:
            target_lang = self.find_first_matching_lang(language)
            logger.bind(tag=TAG).info(f"最终识别语言: {target_lang}")
            # 初始化识别器
            self.recognizer = speechsdk.SpeechRecognizer(speech_config=self.speech_config,
                                                         audio_config=self.audio_config,
                                                         language=target_lang
                                                         )

    def find_first_matching_lang(self, lang_code):

        logger.bind(tag=TAG).info(f"获取客户端源语言: {lang_code}")
        lang_code = _parse_accept_language(lang_code)
        logger.bind(tag=TAG).info(f"转换客户端后目标语言: {lang_code}")

        for code in self.supports_langs:
            if code.startswith(lang_code + '-'):
                return code
        return 'zh-CN'

    async def speech_to_text(self, opus_data, session_id, audio_format):
        try:
            # 1. 解码为 PCM
            if audio_format == "pcm":
                pcm_data = opus_data
            else:
                pcm_data = self.decode_opus(opus_data)
            combined_pcm_data = b"".join(pcm_data)

            logger.bind(tag=TAG).info(f"音频解码完成，开始识别: ")

            self.push_stream.write(combined_pcm_data)
            self.push_stream.close()  # 重要，通知SDK音频已写完

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.recognizer.recognize_once)

            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                logger.bind(tag=TAG).info(f"识别结果: {result.text}")
                return result.text, None
            elif result.reason == speechsdk.ResultReason.NoMatch:
                logger.bind(tag=TAG).warning("音频未匹配到任何语音内容")
                return "", None
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                logger.bind(tag=TAG).error(f"识别被取消: {cancellation_details.reason}")
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    logger.bind(tag=TAG).error(f"错误详情: {cancellation_details.error_details}")
                return "", None
            else:
                logger.bind(tag=TAG).warning(f"未知识别状态: {result.reason}")
                return "", None

        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}", exc_info=True)
            return ""
