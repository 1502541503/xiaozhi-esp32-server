import cnlunar
from plugins_func.register import register_function, ToolType, ActionResponse, Action

get_instruction_function_desc = {
    "type": "function",
    "function": {
        "name": "get_instruction",
        "description": (
            "你是一款多功能智能眼镜设备，旨在提供便捷的用户体验。你可以准确识别用户的意图返回对应的语音命令。"
            "支持的中文语音命令关键词:接听电话,挂断电话,查询电量,拍照,录像,播放音乐,继续播放,暂停播放,上一曲,下一曲,减小音量,增大音量,重启系统,开启勿扰,视觉识别,关闭勿扰,停止录像"
            "比如用户说”我眼前的是什么“”我面前的是什么“”视觉识别“等，你就要返回”视觉识别“。"
            "比如用户说”拍照“”我要拍照“等，你就要返回”拍照“。"
            "比如用户说”录像“”我要录像“等，你就要返回”录像“。"
            "比如用户说”上一首“”上一曲“”播放上一首“等，你就要返回”上一曲“。"
            "比如用户说”下一首“”下一曲“”播放下一首“等，你就要返回”下一曲“。"
            "比如用户说”我要听音乐“”播放音乐“”开始播放音乐“等，你就要返回”播放音乐“。"
            "比如用户说”接听电话“”帮我接听电话“等，你就要返回”接听电话“。"
            "比如用户说”音量调整到20“，有具体的调整数值，你就要返回”音量调整:20“，即是“音量调整:数值”。"
            "如果只返回关键字，不能有任何多余的解释。"
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


@register_function("get_instruction", get_instruction_function_desc, ToolType.WAIT)
def get_instruction():
    print(f"进入语音命令插件")

    return ActionResponse(Action.REQLLM, "根据用户的回答是否是上述语音关键字，是则只返回关键字，否则正常回答", None)