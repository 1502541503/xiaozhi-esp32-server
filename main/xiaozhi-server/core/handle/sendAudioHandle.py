import json
import asyncio
import time
from core.providers.tts.dto.dto import SentenceType
from core.utils.util import get_string_no_punctuation_or_emoji, analyze_emotion
from loguru import logger

TAG = __name__

emoji_map = {
    "neutral": "😶",
    "happy": "🙂",
    "laughing": "😆",
    "funny": "😂",
    "sad": "😔",
    "angry": "😠",
    "crying": "😭",
    "loving": "😍",
    "embarrassed": "😳",
    "surprised": "😲",
    "shocked": "😱",
    "thinking": "🤔",
    "winking": "😉",
    "cool": "😎",
    "relaxed": "😌",
    "delicious": "🤤",
    "kissy": "😘",
    "confident": "😏",
    "sleepy": "😴",
    "silly": "😜",
    "confused": "🙄",
}


async def sendAudioMessage(conn, sentenceType, audios, text):
    # 发送句子开始消息
    start_time = time.time()
    conn.logger.bind(tag=TAG).info(f"发送音频消息: {sentenceType}, {text}")
    if text is not None:
        emotion = analyze_emotion(text)
        emoji = emoji_map.get(emotion, "🙂")  # 默认使用笑脸
        await conn.websocket.send(
            json.dumps(
                {
                    "type": "llm",
                    "text": emoji,
                    "emotion": emotion,
                    "session_id": conn.session_id,
                }
            )
        )

    if text is not None:
        short_cmd_prefixes = [
            "接听电话", "挂断电话", "查询电量", "拍照", "录像", "播放音乐", "继续播放",
            "暂停播放", "上一曲", "下一曲", "减小音量", "增大音量", "重启系统",
            "开启勿扰", "视觉识别", "关闭勿扰", "停止录像", "音量调整",
            "Answer the call", "Hang up the call", "Check the battery level",
            "Take a photo", "Record a video", "Play some music", "Resume playing",
            "Pause the music", "Previous song", "Next song", "Volume down",
            "Volume up", "Restart the device", "Turn on Do Not Disturb",
            "Visual recognition", "Turn off Do Not Disturb", "Stop recording"
        ]
        clean_text = text.strip()
        if any(clean_text.startswith(cmd) for cmd in short_cmd_prefixes):
            conn.logger.bind(tag=TAG).info(f"命令式回答内容（跳过语音）: {clean_text}")
            await send_tts_message(conn, "sentence_start", text)
            await send_tts_message(conn, "sentence_end", text)
            if conn.llm_finish_task and sentenceType == SentenceType.LAST:
                pre_buffer = False
                await send_tts_message(conn, "stop", None)
                conn.client_is_speaking = False
                if conn.close_after_chat:
                    await conn.close()
            return

    pre_buffer = False
    if conn.tts.tts_audio_first_sentence and text is not None:
        elapsed = time.time() - start_time
        conn.logger.bind(tag=TAG).info(f"文本转语音第一帧耗时: {round(elapsed, 3)}")
        await conn.websocket.send(
            json.dumps(
                {
                    "type": "server",
                    "msg": "文本转语音第一帧耗时",
                    "duration": round(elapsed, 3),
                    "session_id": conn.session_id,
                    "model": 3
                }
            )
        )
        conn.logger.bind(tag=TAG).info(f"发送第一段语音: {text}")
        conn.tts.tts_audio_first_sentence = False
        pre_buffer = True

    await send_tts_message(conn, "sentence_start", text)

    await sendAudio(conn, audios, pre_buffer)

    await send_tts_message(conn, "sentence_end", text)

    # 发送结束消息（如果是最后一个文本）
    if conn.llm_finish_task and sentenceType == SentenceType.LAST:
        await send_tts_message(conn, "stop", None)
        conn.client_is_speaking = False
        if conn.close_after_chat:
            await conn.close()


# 播放音频
async def sendAudio(conn, audios, pre_buffer=True):
    if audios is None or len(audios) == 0:
        return
    # 流控参数优化
    frame_duration = 60  # 帧时长（毫秒），匹配 Opus 编码
    start_time = time.perf_counter()
    play_position = 0
    last_reset_time = time.perf_counter()  # 记录最后的重置时间

    # 仅当第一句话时执行预缓冲
    if pre_buffer:
        pre_buffer_frames = min(3, len(audios))
        for i in range(pre_buffer_frames):
            await conn.websocket.send(audios[i])
        remaining_audios = audios[pre_buffer_frames:]
    else:
        remaining_audios = audios

    # 播放剩余音频帧
    for opus_packet in remaining_audios:
        if conn.client_abort:
            break

        # 每分钟重置一次计时器
        if time.perf_counter() - last_reset_time > 60:
            await conn.reset_timeout()
            last_reset_time = time.perf_counter()

        # 计算预期发送时间
        expected_time = start_time + (play_position / 1000)
        current_time = time.perf_counter()
        delay = expected_time - current_time
        if delay > 0:
            await asyncio.sleep(delay)

        await conn.websocket.send(opus_packet)

        play_position += frame_duration


async def send_tts_message(conn, state, text=None):
    """发送 TTS 状态消息"""
    message = {"type": "tts", "state": state, "session_id": conn.session_id}
    if text is not None:
        message["text"] = text

    # TTS播放结束
    if state == "stop":
        # 播放提示音
        # tts_notify = conn.config.get("enable_stop_tts_notify", False)
        # if tts_notify:
        #     stop_tts_notify_voice = conn.config.get(
        #         "stop_tts_notify_voice", "config/assets/tts_notify.mp3"
        #     )
        #     audios, _ = conn.tts.audio_to_opus_data(stop_tts_notify_voice)
        #     await sendAudio(conn, audios)
        # 清除服务端讲话状态
        conn.clearSpeakStatus()

    # 发送消息到客户端
    await conn.websocket.send(json.dumps(message))


async def send_stt_message(conn, text):
    # end_prompt_str = conn.config.get("end_prompt", {}).get("prompt")
    # if end_prompt_str and end_prompt_str == text:
    #     await send_tts_message(conn, "start")
    #     return

    """发送 STT 状态消息"""
    stt_text = get_string_no_punctuation_or_emoji(text)
    await conn.websocket.send(
        json.dumps({"type": "stt", "text": stt_text, "session_id": conn.session_id})
    )
    conn.client_is_speaking = True
    await send_tts_message(conn, "start")
