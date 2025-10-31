import json
import time
import base64
import asyncio

import numpy as np
import websockets
import opuslib_next
import random
from urllib import parse
from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__
logger = setup_logging()


class AccessToken:
    @staticmethod
    def _encode_text(text):
        encoded_text = parse.quote_plus(text)
        return encoded_text.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")

    @staticmethod
    def _encode_dict(dic):
        keys = dic.keys()
        dic_sorted = [(key, dic[key]) for key in sorted(keys)]
        encoded_text = parse.urlencode(dic_sorted)
        return encoded_text.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.silence_frames_sent = 0
        self.last_audio_time = None
        self.interface_type = InterfaceType.STREAM
        self.config = config
        self.text = ""
        self.decoder = opuslib_next.Decoder(16000, 1)
        self.asr_ws = None
        self.forward_task = None
        self.is_processing = False
        self.server_ready = False  # 服务器准备状态
        self.asr_end = False  # 服务器准备状态

        self._voice_stop_handled = False
        self.audio_file = None

        # 基础配置
        #self.appkey = config.get("appkey")
        self.host = config.get("host", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime")

        self.api_key = config.get("appkey")
        self.model = config.get("model")
        self.enable_server_vad = True
        self.headers = [
            ("Authorization", f"Bearer {self.api_key}"),
            ("OpenAI-Beta", "realtime=v1")
        ]

        self.ws_url = f"{self.host}?model={self.model}"
        self.max_sentence_silence = config.get("max_sentence_silence")
        self.output_dir = config.get("output_dir", "./audio_output")
        self.delete_audio_file = delete_audio_file
        self.expire_time = None



    async def open_audio_channels(self, conn):
        await super().open_audio_channels(conn)

    async def receive_audio(self, conn, audio, audio_have_voice):
        conn.asr_audio.append(audio)
        conn.asr_audio = conn.asr_audio[-500:]

        if audio_have_voice:
            self.last_audio_time = time.time()

        # 参考豆包ASR：只在有声音且没有连接时建立连接
        if audio_have_voice and not self.is_processing:
            try:
                # 初始化 PCM 缓存
                conn.pcm_data = []
                await self._start_recognition(conn)

            except Exception as e:
                logger.bind(tag=TAG).error(f"开始识别失败: {str(e)}")
                await self._cleanup()
                return

        if self.asr_ws and self.is_processing and self.server_ready:
            try:
                pcm_frame = self.decoder.decode(audio, 960)
                encoded_data = base64.b64encode(pcm_frame).decode('utf-8')
                res = {
                    "event_id": f"event_{int(time.time() * 1000)}",
                    "type": "input_audio_buffer.append",
                    "audio": encoded_data
                }
                await self.asr_ws.send(json.dumps(res))
                conn.pcm_data.append(pcm_frame)

            except Exception as e:
                logger.bind(tag=TAG).warning(f"发送音频失败: {str(e)}")
                await self._cleanup()

    async def _start_recognition(self, conn):
        print("开始识别了")
        # self.silence_check_task = asyncio.create_task(self._check_silence_timeout(conn))
        if self.asr_ws and self.is_processing:  # 防止重复进入
            logger.bind(tag=TAG).warning("已有识别进行中，忽略新的 start")
            return
        self.silence_check_task = asyncio.create_task(self._check_silence_timeout(conn, timeout_seconds=2.5))

        """开始识别会话"""

        # 建立连接
        self.asr_ws = await websockets.connect(
            self.ws_url,
            additional_headers=self.headers,
            max_size=1000000000,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=10,
        )

        self.is_processing = True
        self.server_ready = False  # 重置服务器准备状态
        self.forward_task = asyncio.create_task(self._forward_results(conn))

        event_vad = {
            "event_id": "event_123",
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "input_audio_format": "pcm",
                "sample_rate": 16000,
                "input_audio_transcription": {
                    "language": conn.language,
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "silence_duration_ms": 1000
                }
            }
        }
        await self.asr_ws.send(json.dumps(event_vad, ensure_ascii=False))
        logger.bind(tag=TAG).info("已发送开始请求，等待服务器准备...")

    async def _forward_results(self, conn):
        """转发识别结果"""
        last_result_time = time.time()
        #last_result_time = None
        self.silence_frames_sent = 0
        confirmed_text = ""
        try:
            while self.asr_ws and not conn.stop_event.is_set():
                try:
                    response = await asyncio.wait_for(self.asr_ws.recv(), timeout=2.0)
                    result = json.loads(response)
                    #print(f"result==={result}")
                    type = result.get("type", "")
                    last_data_time = time.time()

                    if type == "error" or type == "conversation.item.input_audio_transcription.failed":
                        logger.bind(tag=TAG).warning(f"语言识别异常，状态码: {result}")
                        continue
                    if type == "conversation.item.created":
                        self.silence_frames_sent = 0
                    if type == "session.updated":
                        self.server_ready = True
                        self.silence_frames_sent = 0
                        logger.bind(tag=TAG).info("服务器已准备，开始发送缓存音频...")
                        # 第一次收到服务器准备，初始化 last_result_time
                        # last_result_time = time.time()
                        # 发送缓存音频
                        # print(f"asr_audio===={conn.asr_audio}")
                        if conn.asr_audio:
                            for cached_audio in conn.asr_audio[-100:]:
                                try:
                                    pcm_frame = self.decoder.decode(cached_audio, 960)
                                    encoded_data = base64.b64encode(pcm_frame).decode('utf-8')
                                    res = {
                                        "event_id": f"event_{int(time.time() * 1000)}",
                                        "type": "input_audio_buffer.append",
                                        "audio": encoded_data
                                    }
                                    await self.asr_ws.send(json.dumps(res))
                                except Exception as e:
                                    logger.bind(tag=TAG).warning(f"发送缓存音频失败: {e}")
                                    break
                    if type == "conversation.item.input_audio_transcription.text":
                        fixed = result.get("text", "")
                        stash = result.get("stash", "")
                        if fixed and fixed != confirmed_text:
                            confirmed_text = fixed
                            await conn.websocket.send(json.dumps({
                                "type": "stt2",
                                "state": "sentence_start",
                                "text": confirmed_text,
                                "session_id": conn.session_id
                            }))
                            #logger.bind(tag=TAG).info(f"固定识别结果: {confirmed_text}")

                            # 临时部分（可能变化）
                        if stash:
                            live_text = confirmed_text + stash
                            await conn.websocket.send(json.dumps({
                                "type": "stt2",
                                "state": "sentence_start",
                                "text": live_text,
                                "session_id": conn.session_id
                            }))
                            #logger.bind(tag=TAG).info(f"临时识别结果: {live_text}")
                        continue
                        # text = result.get("text", "")
                        # stash = result.get("stash", "")
                        # logger.bind(tag=TAG).warning(f"中间返回结果: {text}")
                        # if text or stash:
                        #     await conn.websocket.send(
                        #         json.dumps(
                        #             {"type": "stt2", "state": "sentence_start", "text": text, "session_id": conn.session_id}))
                        #     self.asr_end = True
                        #     self.text = text
                        #     last_result_time = time.time()
                        #     continue
                    if type == "conversation.item.input_audio_transcription.completed":
                        # 最终结果
                        text = result.get("transcript", "")
                        logger.bind(tag=TAG).warning(f"最终返回结果: {text}")
                        self.asr_end = True
                        if text:
                            self.text = text
                            await conn.websocket.send(
                                json.dumps(
                                    {"type": "stt2", "state": "sentence_start", "text": text,
                                     "session_id": conn.session_id}))

                            conn.reset_vad_states()
                            conn.asr_audio.clear()
                            print(f"是否保存asr:{self.delete_audio_file}")
                            # === 保存完整 PCM 数据到 wav ===
                            if hasattr(conn, "pcm_data") and conn.pcm_data:
                                if not self.delete_audio_file:
                                    file_path = self.save_audio_to_file(conn.pcm_data, session_id=conn.session_id)
                                    logger.info(f"已保存音频: {file_path}")
                                conn.pcm_data.clear()

                            await self.safe_handle_voice_stop(conn, None)

                            last_result_time = None
                            self.silence_frames_sent = 0
                            break
                        await self._cleanup()

                except asyncio.TimeoutError:
                    now = time.time()
                    #logger.info(f"=====触发了超时===={self.silence_frames_sent}")
                    if self.silence_frames_sent < 3:  # 最多补3次，每次400ms ≈ 1200ms
                        silence = generate_silence(500)
                        encoded_silence = base64.b64encode(silence).decode('utf-8')
                        res = {
                            "event_id": f"event_{int(time.time() * 1000)}",
                            "type": "input_audio_buffer.append",
                            "audio": encoded_silence
                        }
                        await self.asr_ws.send(json.dumps(res))
                        # await self.asr_ws.send(silence)
                        self.silence_frames_sent += 1
                        logger.info(f"补静音第{self.silence_frames_sent}次 (400ms)")
                        continue
                    continue
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    logger.bind(tag=TAG).error(f"处理结果失败: {str(e)}")
                    break

        except Exception as e:
            logger.bind(tag=TAG).error(f"结果转发失败: {str(e)}")
        finally:
            await self._cleanup()

    async def _cleanup(self):
        """清理资源"""
        # print("asr清理资源")
        self._voice_stop_handled = False
        self.is_processing = False
        self.server_ready = False  # 重置服务器准备状态
        self.text = ""
        if hasattr(self, "silence_check_task") and not self.silence_check_task.done():
            self.silence_check_task.cancel()

        if self.forward_task and not self.forward_task.done():
            self.forward_task.cancel()
            try:
                await asyncio.wait_for(self.forward_task, timeout=1.0)
            except:
                pass
            self.forward_task = None

        if self.asr_ws:
            try:
                await asyncio.wait_for(self.asr_ws.close(), timeout=2.0)
            except:
                pass
            self.asr_ws = None

    async def speech_to_text(self, opus_data, session_id, audio_format, language: str = None):
        """获取识别结果"""
        result = self.text
        self.text = ""
        return result, None

    async def close(self):
        """关闭资源"""
        await self._cleanup()

    async def _check_silence_timeout(self, conn, timeout_seconds=2.0):
        """无音频输入超过 timeout_seconds，则结束识别"""
        while self.is_processing:
            await asyncio.sleep(0.1)  # 频率可以更高一些，减少延迟
            now = time.time()
            if self.last_audio_time is None:
                # 如果还没收到过音频，等1秒后也结束
                await asyncio.sleep(timeout_seconds)
                logger.bind(tag=TAG).info("1秒内无音频输入，自动停止识别")
                await self._stop_recognition(conn)
                break
            elif now - self.last_audio_time > timeout_seconds:
                logger.bind(tag=TAG).info(f"静音超过{timeout_seconds}秒，自动停止识别")
                await self._stop_recognition(conn)
                break

    async def _stop_recognition(self, conn):
        """手动停止识别流程"""
        print("===手动停止了===")
        if self.asr_ws:
            try:
                stop_request = {
                    "header": {
                        "namespace": "SpeechTranscriber",
                        "name": "StopTranscription",
                        "status": 20000000,
                        "message_id": ''.join(random.choices('0123456789abcdef', k=32)),
                    }
                }
                await self.asr_ws.send(json.dumps(stop_request))
                logger.bind(tag=TAG).info("已发送 Stop 请求")
            except Exception as e:
                logger.bind(tag=TAG).warning(f"发送 Stop 请求失败: {e}")

        if self.asr_ws and conn.asr_audio:
            try:
                pcm_frame = self.decoder.decode(conn.asr_audio[-1], 960)
                # pcm_frame = self.decoder.decode(cached_audio, 960)
                encoded_data = base64.b64encode(pcm_frame).decode('utf-8')
                res = {
                    "event_id": f"event_{int(time.time() * 1000)}",
                    "type": "input_audio_buffer.append",
                    "audio": encoded_data
                }
                await self.asr_ws.send(json.dumps(res))
                logger.bind(tag=TAG).info("Stop 前补发最后一帧音频")
            except Exception as e:
                logger.bind(tag=TAG).warning(f"Stop 前补发失败: {e}")
        # 清理
        self.is_processing = False
        self.server_ready = False

    async def safe_handle_voice_stop(self, conn, arg):
        if self._voice_stop_handled:
            logger.bind(tag=TAG).info("handle_voice_stop 已处理，跳过重复调用")
            return
        stop_request = {
            "header": {
                "namespace": "SpeechTranscriber",
                "name": "StopTranscription",
                "status": 20000000,
                #"appkey": self.appkey,
                "message_id": ''.join(random.choices('0123456789abcdef', k=32)),
            }
        }
        await self.asr_ws.send(json.dumps(stop_request))
        logger.bind(tag=TAG).info("已发送 Stop 请求")
        self._voice_stop_handled = False
        await self.handle_voice_stop(conn, arg)
        # 清理
        self.is_processing = False
        self.server_ready = False


def generate_silence(duration_ms=300, sample_rate=16000):
    """生成指定时长的静音 PCM"""
    num_samples = int(sample_rate * duration_ms / 1000)
    silence = np.zeros(num_samples, dtype=np.int16)
    return silence.tobytes()
