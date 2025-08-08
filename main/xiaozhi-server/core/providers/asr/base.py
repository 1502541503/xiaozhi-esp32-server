import json
import os
import time
import wave
import copy
import uuid
import queue
import asyncio
import traceback
import threading
import opuslib_next
from abc import ABC, abstractmethod
from config.logger import setup_logging
from typing import Optional, Tuple, List
from core.handle.receiveAudioHandle import startToChat
from core.handle.reportHandle import enqueue_asr_report
from core.utils.util import remove_punctuation_and_length
from core.handle.receiveAudioHandle import handleAudioMessage
from concurrent.futures import ThreadPoolExecutor

TAG = __name__
logger = setup_logging()


class ASRProviderBase(ABC):
    TAG = "ASRProviderBase"

    def __init__(self):
        pass

    # 打开音频通道
    # 这里默认是非流式的处理方式
    # 流式处理方式请在子类中重写
    async def open_audio_channels(self, conn):
        # tts 消化线程
        conn.asr_priority_thread = threading.Thread(
            target=self.asr_text_priority_thread, args=(conn,), daemon=True
        )
        conn.asr_priority_thread.start()

    # 有序处理ASR音频
    def asr_text_priority_thread(self, conn):

        while not conn.stop_event.is_set():
            try:
                message = conn.asr_audio_queue.get(timeout=1)

                future = asyncio.run_coroutine_threadsafe(
                    handleAudioMessage(conn, message),
                    conn.loop,
                )
                future.result()
            except queue.Empty:
                continue
            except Exception as e:
                conn.websocket.send(json.dumps(
                    {
                        "type": "server",
                        "code": 4001,
                        "msg": f"处理ASR文本失败: {str(e)}",
                        "session_id": conn.session_id,
                    }
                ))
                logger.bind(tag=TAG).error(
                    f"处理ASR文本失败: {str(e)}, 类型: {type(e).__name__}, 堆栈: {traceback.format_exc()}"
                )
                continue

    # 接收音频
    # 这里默认是非流式的处理方式
    # 流式处理方式请在子类中重写
    async def receive_audio(self, conn, audio, audio_have_voice):
        #print(f"开始接收音频===={audio_have_voice}")
        await conn.websocket.send(json.dumps(
            {
                "type": "server",
                "code": 0,
                "msg": "接收到了音频流",
                "session_id": conn.session_id,
            }
        ))
        if not hasattr(conn, "audio_timeout_triggered"):
            print(f"audio_timeout_triggered = False")
            conn.audio_timeout_triggered = False
        if conn.client_listen_mode == "auto" or conn.client_listen_mode == "realtime":
            have_voice = audio_have_voice
        else:
            have_voice = conn.client_have_voice
        # 如果本次没有声音，本段也没声音，就把声音丢弃了
        conn.asr_audio.append(audio)
        if have_voice == False and conn.client_have_voice == False:
            conn.asr_audio = conn.asr_audio[-100:]
            #print(f"本次接受的音频没有声音，本段也没声音，把声音丢弃.have_voice={have_voice}.client_have_voice={conn.client_have_voice}")
            if not conn.audio_timeout_triggered:
                if hasattr(conn, "audio_timeout_task"):
                    conn.audio_timeout_task.cancel()
                conn.audio_timeout_task = asyncio.create_task(self._audio_no_checker(conn))
            return
        # 如果本段有声音，且已经停止了
        if conn.client_voice_stop:

            print(f"本段有声音，且已经停止了")
            asr_audio_task = copy.deepcopy(conn.asr_audio)
            conn.asr_audio.clear()

            # 音频太短了，无法识别
            conn.reset_vad_states()
            if len(asr_audio_task) > 15:
                conn.audio_timeout_triggered = True
                if hasattr(conn, "audio_timeout_task"):
                    conn.audio_timeout_task.cancel()
                await self.handle_voice_stop(conn, asr_audio_task)
            else:
                conn.logger.bind(tag=TAG).info("[receive_audio] 音频帧太短，忽略本段")
            return

        if not conn.audio_timeout_triggered:
            if hasattr(conn, "audio_timeout_task"):
                conn.audio_timeout_task.cancel()
            conn.audio_timeout_task = asyncio.create_task(self._audio_timeout_checker(conn))

    # 处理语音停止
    async def handle_voice_stop(self, conn, asr_audio_task):
        print("进入====handle_voice_stop")
        if asr_audio_task and len(asr_audio_task) < 10:
            conn.logger.bind(tag=TAG).warning("识别结果太短，跳过对话处理")
            return
        raw_text, _ = await self.speech_to_text(
            asr_audio_task, conn.session_id, conn.audio_format
        )  # 确保ASR模块返回原始文本

        conn.logger.bind(tag=TAG).info(f"识别文本: {raw_text}")
        text_len, _ = remove_punctuation_and_length(raw_text)

        if text_len < 2:
            conn.logger.bind(tag=TAG).warning(f"识别结果过短（{text_len} 个字），跳过对话触发")
            return

        self.stop_ws_connection()
        if text_len > 0:
            # 使用自定义模块进行上报
            await startToChat(conn, raw_text)
            enqueue_asr_report(conn, raw_text, asr_audio_task)

    async def _audio_timeout_checker(self, conn):
        try:
            await asyncio.sleep(1)  # 设置超时时间（秒）
            if getattr(conn, "audio_timeout_triggered", False):
                return  # 已触发识别，跳过
            if len(conn.asr_audio) > 15:
                conn.logger.bind(tag=TAG).info("超时未收到音频，自动触发识别")
                conn.audio_timeout_triggered = True
                await self.handle_voice_stop(conn, copy.deepcopy(conn.asr_audio))
                conn.asr_audio.clear()
        except asyncio.CancelledError:
            # 收到新音频帧后取消
            pass

    async def _audio_no_checker(self, conn):
        try:
            await asyncio.sleep(1)  # 设置超时时间（秒）
            conn.logger.bind(tag=TAG).info(f"整段都没声音，且后续客户端无音频推送:{len(conn.asr_audio)}")
            if len(conn.asr_audio)==100:
                await conn.websocket.send(json.dumps(
                    {
                        "type": "server",
                        "code": 4002,
                        "msg": "整段音频无声音，并后续无音频推送",
                        "session_id": conn.session_id,
                    }
                ))
                conn.asr_audio.clear()

            conn.audio_timeout_triggered = False
        except asyncio.CancelledError:
            # 收到新音频帧后取消
            pass

    def stop_ws_connection(self):
        pass

    def save_audio_to_file(self, pcm_data: List[bytes], session_id: str) -> str:
        """PCM数据保存为WAV文件"""
        module_name = __name__.split(".")[-1]
        file_name = f"asr_{module_name}_{session_id}_{uuid.uuid4()}.wav"
        file_path = os.path.join(self.output_dir, file_name)

        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 2 bytes = 16-bit
            wf.setframerate(16000)
            wf.writeframes(b"".join(pcm_data))

        return file_path

    @abstractmethod
    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, audio_format="opus"
    ) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本"""
        pass

    @staticmethod
    def decode_frame(decoder_args):
        decoder, opus_packet, index = decoder_args
        try:
            pcm_frame = decoder.decode(opus_packet, 960)
            return pcm_frame
        except Exception as e:
            logger.bind(tag=ASRProviderBase.TAG).warning(f"解码包 {index} 异常: {e}")
            return b""

    @staticmethod
    def decode_opus(opus_data: List[bytes]) -> bytes:
        """将Opus音频数据解码为PCM数据"""
        logger.bind(tag=ASRProviderBase.TAG).warning("将Opus音频数据解码为PCM数据")
        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                decoder_list = [opuslib_next.Decoder(16000, 1) for _ in range(len(opus_data))]
                results = executor.map(ASRProviderBase.decode_frame, zip(decoder_list, opus_data, range(len(opus_data))))
                return list(results)
        except Exception as e:
            logger.bind(tag=ASRProviderBase.TAG).error(f"音频解码过程发生错误: {e}", exc_info=True)
            return []