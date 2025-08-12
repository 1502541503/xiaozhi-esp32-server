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


def _parse_accept_language(accept_language_header: str) -> str:
    """
    解析 Accept-Language 头部，提取主要语言代码

    Args:
        accept_language_header: Accept-Language 头部值，如 'zh-CN,zh;q=0.9' 或 'zh,en'

    Returns:
        str: 提取的主要语言代码，如 'zh', 'en' 等
    """
    if not accept_language_header:
        return None

    # 分割语言选项
    languages = accept_language_header.split(',')

    if not languages:
        return None

    # 获取第一个语言选项（权重最高或第一个列出的）
    primary_language = languages[0].strip()

    # 移除质量值部分 (q=x.x)
    if ';' in primary_language:
        primary_language = primary_language.split(';')[0]

    # 如果包含连字符，提取主要语言部分
    if '-' in primary_language:
        primary_language = primary_language.split('-')[0]

    # 确保返回小写格式
    return primary_language.lower() if primary_language else None


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

    async def speech_to_text(self, opus_data: List[bytes], session_id: str, audio_format="opus",
                             language: str = None) -> tuple[
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
                lang = _parse_accept_language(language)

                result_text = await self._transcribe_with_whisper(file_path, lang)

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

    async def _transcribe_with_whisper(self, audio_file_path: str, lang: str = None) -> str:
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

                logger.bind(tag=TAG).info(f"Whisper 获取最终识别语种：{lang}")
                form_data.add_field('language', lang)  # 根据请求头设置识别语种

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
