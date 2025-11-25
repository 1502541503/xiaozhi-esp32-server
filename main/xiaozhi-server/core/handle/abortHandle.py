import json

TAG = __name__


async def handleAbortMessage(conn):
    conn.logger.bind(tag=TAG).info("Abort message received")
    # 设置成打断状态
    conn.client_abort = True
    # 清空asr音频缓存
    conn.reset_vad_states()
    conn.asr_audio.clear()
    await conn.asr._cleanup()
    # 清空tts队列
    conn.clear_queues()
    conn.clearSpeakStatus()
    conn.is_processing = False
    conn.server_ready = False
    conn.client_have_voice = True

    # 打断客户端说话状态
    await conn.websocket.send(
        json.dumps({"type": "tts", "state": "stop", "session_id": conn.session_id})
    )
