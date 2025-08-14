import cnlunar
from plugins_func.register import register_function, ToolType, ActionResponse, Action

#"支持的中文语音命令关键词:0x01:接听电话,0x02:挂断电话,0x03:查询电量,0x04:拍照,0x05:录像,0x07:播放音乐,0x08:继续播放,0x01:暂停播放,上一曲,下一曲,减小音量,增大音量,重启系统,开启勿扰,视觉识别,关闭勿扰,停止录像"
get_instruction_function_desc = {
    "type": "function",
    "function": {
        "name": "get_instruction_en",
        "description": (
            "You are a multifunctional smart glasses device designed to provide a convenient user experience. You can accurately recognize users' intentions and return corresponding voice commands."
            "Supported English voice command keywords:0x01:Answer the call,0x02:Hang up the call,0x04:Enable photography,0x05:Start Video recording,0x07:Play music,0x08:Resume Playing,0x09:Pause,0x0A:Previous song,0x0B:Next song,0x0C:Volume down,0x0D:Volume up,0x11:Visual recognization,0x06:Stop Video recording"
            "For example, if the user says ‘What is in front of me?’, ‘What is in front of me?’, ‘Visual recognition’, etc., you should return ‘0x11:Visual recognization’."
            "For example, if the user says 'take a photo' or 'I want to take a photo', you should respond with '0x04:Enable photography'."
            "For example, if the user says 'Record' or 'I want to record', you should respond with '0x05:Start Video recording'."
            "For example, if the user says 'previous song', 'previous track', 'play previous song', etc., you should respond with '0x0A:Previous song'."
            "For example, if the user says 'next song', 'next track', 'play the next song', etc., you should respond with '0x0B:Next song'."
            "For example, if the user says 'I want to listen to music', 'play music', 'start playing music', etc., you should respond with '0x07:Play music'."
            "For example, if the user says 'answer the call' or 'help me answer the call', you should respond with '0x01:Answer the call'."
            "For example, if the user says 'Adjust the volume to 20', which has a specific adjustment value, you should return '0x00:Volume Adjustment:20', which is '0x00:Volume Adjustment:Value'."
            "You can only answer the above voice command keywords without adding any extra explanations."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


@register_function("get_instruction_en", get_instruction_function_desc, ToolType.WAIT)
def get_instruction():
    print(f"进入英文语音命令插件")

    return ActionResponse(Action.REQLLM, "According to whether the user's answer is the aforementioned voice keyword, if yes, only the keyword will be returned, and unnecessary words are not allowed.", None)