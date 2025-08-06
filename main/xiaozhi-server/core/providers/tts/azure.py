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

        self.output_file = config.get("output_dir", "tmp/")

        # 验证必要配置
        if not self.api_key:
            raise ValueError("Azure OpenAI TTS api_key is required")

        # 确保输出目录存在
        if not os.path.exists(self.output_file):
            try:
                os.makedirs(self.output_file, exist_ok=True)
            except Exception as e:
                # 如果配置的目录无法创建，使用当前工作目录下的 tmp 文件夹
                self.output_file = os.path.join(os.getcwd(), "tmp")
                os.makedirs(self.output_file, exist_ok=True)

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
                            # 确保输出目录存在
                            output_dir = os.path.dirname(output_file)
                            if output_dir and not os.path.exists(output_dir):
                                os.makedirs(output_dir, exist_ok=True)

                            with open(output_file, "wb") as audio_file:
                                audio_file.write(content)
                            logger.bind(tag=TAG).info(f"Azure OpenAI TTS 合成已完成，文本: {text[:30]}...")
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
