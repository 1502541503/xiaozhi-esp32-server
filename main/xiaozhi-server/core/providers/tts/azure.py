import os
import aiohttp
import time
from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url")
        self.model = config.get("model")
        self.voice = config.get("voice", "alloy")
        self.api_version = config.get("api_version", "2025-04-01-preview")

        self.output_file = "tmp/"

        # 验证必要配置
        if not self.api_key:
            raise ValueError("Azure OpenAI TTS api_key is required")


    def generate_filename(self, extension=".mp3"):
        """生成唯一的音频文件名"""
        return os.path.join(self.output_file, f"azure_openai_tts_{os.urandom(4).hex()}{extension}")

    async def text_to_speak(self, text, output_file):
        """调用Azure OpenAI TTS API将文本转换为语音"""
        logger.bind(tag=TAG).info(f"开始Azure OpenAI TTS合成，文本长度: {len(text)}")

        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json"
        }

        # 构造请求数据
        payload = {
            "model": self.model,
            "input": text,
            "voice": self.voice
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        self.base_url,
                        headers=headers,
                        json=payload
                ) as response:
                    if response.status == 200:
                        content = await response.read()
                        if output_file:
                            self.save_audio_to_file(content, output_file)
                        return output_file
                    else:
                        error_text = await response.text()
                        logger.bind(tag=TAG).error(f"Azure OpenAI TTS请求失败: {response.status}")
                        logger.bind(tag=TAG).error(f"请求数据: {payload}")
                        logger.bind(tag=TAG).error(f"错误详情: {error_text}")
                        raise Exception(
                            f"Azure OpenAI TTS请求失败: {response.status} - 错误信息: {error_text}")

        except Exception as e:
            logger.bind(tag=TAG).error(f"Azure OpenAI TTS请求异常: {e}", exc_info=True)
            raise Exception(f"Azure OpenAI TTS请求异常: {e}")
