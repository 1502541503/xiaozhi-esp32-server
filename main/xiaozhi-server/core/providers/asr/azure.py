import asyncio
import aiohttp
import os
from typing import List

from core.providers.asr.base import ASRProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

MAX_RETRIES = 2
RETRY_DELAY = 1  # 重试延迟（秒）


class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.config = config
        self.delete_audio_file = delete_audio_file

        # Azure OpenAI 配置
        self.api_key = config.get("api_key")
        # 构建API URL
        self.base_url = config.get("base_url")

        # 验证必要配置
        if not self.api_key:
            raise ValueError("Azure OpenAI ASR api_key is required")


        # 临时文件目录
        self.temp_dir = config.get("temp_dir", "tmp/")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)

    def _save_audio_to_temp_file(self, pcm_data: bytes, session_id: str) -> str:
        """将PCM数据保存为临时WAV文件"""
        import wave

        file_path = os.path.join(self.temp_dir, f"asr_temp_{session_id}.wav")

        # 将PCM数据写入WAV文件
        with wave.open(file_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # 单声道
            wav_file.setsampwidth(2)  # 16位
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(pcm_data)

        return file_path

    async def speech_to_text(self, opus_data: List[bytes], session_id: str, audio_format="opus") -> tuple[
                                                                                                        str, None] | None:
        """语音转文本主处理逻辑"""
        file_path = None
        retry_count = 0

        while retry_count < MAX_RETRIES:
            try:
                # 1. 解码为 PCM
                if audio_format == "pcm":
                    pcm_data = b"".join(opus_data)
                else:
                    pcm_data = b"".join(self.decode_opus(opus_data))

                # 2. 保存为临时WAV文件
                file_path = self._save_audio_to_temp_file(pcm_data, session_id)
                logger.bind(tag=TAG).debug(f"音频已保存到临时文件: {file_path}")

                # 3. 调用Azure OpenAI Whisper API
                result_text = await self._transcribe_with_whisper(file_path)

                # 4. 删除临时文件（如果需要）
                if self.delete_audio_file and file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.bind(tag=TAG).debug(f"已删除临时文件: {file_path}")
                    except Exception as e:
                        logger.bind(tag=TAG).warning(f"删除临时文件失败: {e}")

                return result_text, None

            except Exception as e:
                retry_count += 1
                logger.bind(tag=TAG).error(f"语音识别失败 (尝试 {retry_count}/{MAX_RETRIES}): {e}", exc_info=True)

                if retry_count < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    # 最后一次尝试也失败了
                    if self.delete_audio_file and file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as remove_error:
                            logger.bind(tag=TAG).warning(f"删除临时文件失败: {remove_error}")
                    return "", None

        return None

    async def _transcribe_with_whisper(self, audio_file_path: str) -> str:
        """使用Azure OpenAI Whisper模型进行语音转文本"""
        try:
            headers = {
                "api-key": self.api_key,
            }

            # 准备multipart/form-data请求
            with open(audio_file_path, 'rb') as audio_file:
                form_data = aiohttp.FormData()
                form_data.add_field('file', audio_file, filename=os.path.basename(audio_file_path))
                form_data.add_field('response_format', 'json')
                form_data.add_field('language', 'zh')  # 可以根据需要调整或移除

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                            self.base_url,
                            headers=headers,
                            data=form_data
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            text = result.get('text', '')
                            logger.bind(tag=TAG).info(f"Whisper识别成功，文本长度: {len(text)}")
                            return text
                        else:
                            error_text = await response.text()
                            logger.bind(tag=TAG).error(f"Whisper API请求失败: {response.status} - {error_text}")
                            raise Exception(f"Whisper API请求失败: {response.status} - {error_text}")

        except Exception as e:
            logger.bind(tag=TAG).error(f"Whisper转录失败: {e}", exc_info=True)
            raise Exception(f"Whisper转录失败: {e}")
