import json
import socket
import subprocess
import re
import os
import wave
from io import BytesIO
from core.utils import p3
import numpy as np
import requests
import opuslib_next
from typing import Callable, Any
from pydub import AudioSegment
import copy

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

def pcm_to_data_stream(raw_data, is_opus=True, callback: Callable[[Any], Any] = None):
    # 初始化Opus编码器
    encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)

    # 编码参数
    frame_duration = 60  # 60ms per frame
    frame_size = int(16000 * frame_duration / 1000)  # 960 samples/frame

    # 按帧处理所有音频数据（包括最后一帧可能补零）
    for i in range(0, len(raw_data), frame_size * 2):  # 16bit=2bytes/sample
        # 获取当前帧的二进制数据
        chunk = raw_data[i : i + frame_size * 2]

        # 如果最后一帧不足，补零
        if len(chunk) < frame_size * 2:
            chunk += b"\x00" * (frame_size * 2 - len(chunk))

        if is_opus:
            # 转换为numpy数组处理
            np_frame = np.frombuffer(chunk, dtype=np.int16)
            # 编码Opus数据
            frame_data = encoder.encode(np_frame.tobytes(), frame_size)
            callback(frame_data)
        else:
            frame_data = chunk if isinstance(chunk, bytes) else bytes(chunk)
            callback(frame_data)

def audio_to_data_stream(audio_file_path, is_opus=True, callback: Callable[[Any], Any]=None) -> None:
    # 获取文件后缀名
    file_type = os.path.splitext(audio_file_path)[1]
    if file_type:
        file_type = file_type.lstrip(".")
    # 读取音频文件，-nostdin 参数：不要从标准输入读取数据，否则FFmpeg会阻塞
    audio = AudioSegment.from_file(
        audio_file_path, format=file_type, parameters=["-nostdin"]
    )

    # 转换为单声道/16kHz采样率/16位小端编码（确保与编码器匹配）
    audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)

    # 获取原始PCM数据（16位小端）
    raw_data = audio.raw_data
    pcm_to_data_stream(raw_data, is_opus, callback)

def audio_bytes_to_data_stream(audio_bytes, file_type, is_opus, callback: Callable[[Any], Any]) -> None:
    """
    直接用音频二进制数据转为opus/pcm数据，支持wav、mp3、p3
    """
    if file_type == "p3":
        # 直接用p3解码
        return p3.decode_opus_from_bytes_stream(audio_bytes, callback)
    else:
        # 其他格式用pydub
        audio = AudioSegment.from_file(
            BytesIO(audio_bytes), format=file_type, parameters=["-nostdin"]
        )
        audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        raw_data = audio.raw_data
        pcm_to_data_stream(raw_data, is_opus, callback)

"""
解析 Accept-Language 头部，提取主要语言代码

Args:
    accept_language_header: Accept-Language 头部值，如 'zh-CN,zh;q=0.9' 或 'zh,en'

Returns:
    str: 提取的主要语言代码，如 'zh', 'en' 等
"""
def _parse_accept_language(accept_language_header: str) -> str:

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

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to Google's DNS servers
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception as e:
        return "127.0.0.1"


def is_private_ip(ip_addr):
    """
    Check if an IP address is a private IP address (compatible with IPv4 and IPv6).

    @param {string} ip_addr - The IP address to check.
    @return {bool} True if the IP address is private, False otherwise.
    """
    try:
        # Validate IPv4 or IPv6 address format
        if not re.match(
            r"^(\d{1,3}\.){3}\d{1,3}$|^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$", ip_addr
        ):
            return False  # Invalid IP address format

        # IPv4 private address ranges
        if "." in ip_addr:  # IPv4 address
            ip_parts = list(map(int, ip_addr.split(".")))
            if ip_parts[0] == 10:
                return True  # 10.0.0.0/8 range
            elif ip_parts[0] == 172 and 16 <= ip_parts[1] <= 31:
                return True  # 172.16.0.0/12 range
            elif ip_parts[0] == 192 and ip_parts[1] == 168:
                return True  # 192.168.0.0/16 range
            elif ip_addr == "127.0.0.1":
                return True  # Loopback address
            elif ip_parts[0] == 169 and ip_parts[1] == 254:
                return True  # Link-local address 169.254.0.0/16
            else:
                return False  # Not a private IPv4 address
        else:  # IPv6 address
            ip_addr = ip_addr.lower()
            if ip_addr.startswith("fc00:") or ip_addr.startswith("fd00:"):
                return True  # Unique Local Addresses (FC00::/7)
            elif ip_addr == "::1":
                return True  # Loopback address
            elif ip_addr.startswith("fe80:"):
                return True  # Link-local unicast addresses (FE80::/10)
            else:
                return False  # Not a private IPv6 address

    except (ValueError, IndexError):
        return False  # IP address format error or insufficient segments


def get_ip_info(ip_addr, logger):
    try:
        if is_private_ip(ip_addr):
            ip_addr = ""
        url = f"https://whois.pconline.com.cn/ipJson.jsp?json=true&ip={ip_addr}"
        resp = requests.get(url).json()
        ip_info = {"city": resp.get("city")}
        return ip_info
    except Exception as e:
        logger.bind(tag=TAG).error(f"Error getting client ip info: {e}")
        return {}


def write_json_file(file_path, data):
    """将数据写入 JSON 文件"""
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def is_punctuation_or_emoji(char):
    """检查字符是否为空格、指定标点或表情符号"""
    # 定义需要去除的中英文标点（包括全角/半角）
    punctuation_set = {
        "，",
        ",",  # 中文逗号 + 英文逗号
        "-",
        "－",  # 英文连字符 + 中文全角横线
        "、",  # 中文顿号
        "“",
        "”",
        '"',  # 中文双引号 + 英文引号
        "：",
        ":",  # 中文冒号 + 英文冒号
    }
    if char.isspace() or char in punctuation_set:
        return True
    # 检查表情符号（保留原有逻辑）
    code_point = ord(char)
    emoji_ranges = [
        (0x1F600, 0x1F64F),
        (0x1F300, 0x1F5FF),
        (0x1F680, 0x1F6FF),
        (0x1F900, 0x1F9FF),
        (0x1FA70, 0x1FAFF),
        (0x2600, 0x26FF),
        (0x2700, 0x27BF),
    ]
    return any(start <= code_point <= end for start, end in emoji_ranges)


def get_string_no_punctuation_or_emoji(s):
    """去除字符串首尾的空格、标点符号和表情符号"""
    chars = list(s)
    # 处理开头的字符
    start = 0
    while start < len(chars) and is_punctuation_or_emoji(chars[start]):
        start += 1
    # 处理结尾的字符
    end = len(chars) - 1
    while end >= start and is_punctuation_or_emoji(chars[end]):
        end -= 1
    return "".join(chars[start : end + 1])


def remove_punctuation_and_length(text):
    # 全角符号和半角符号的Unicode范围
    full_width_punctuations = (
        "！＂＃＄％＆＇（）＊＋，－。／：；＜＝＞？＠［＼］＾＿｀｛｜｝～"
    )
    half_width_punctuations = r'!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~'
    space = " "  # 半角空格
    full_width_space = "　"  # 全角空格

    # 去除全角和半角符号以及空格
    result = "".join(
        [
            char
            for char in text
            if char not in full_width_punctuations
            and char not in half_width_punctuations
            and char not in space
            and char not in full_width_space
        ]
    )

    if result == "Yeah":
        return 0, ""
    return len(result), result


def check_model_key(modelType, modelKey):
    if "你" in modelKey:
        raise ValueError(
            "你还没配置" + modelType + "的密钥，请检查一下所使用的LLM是否配置了密钥"
        )
    return True


def parse_string_to_list(value, separator=";"):
    """
    将输入值转换为列表
    Args:
        value: 输入值，可以是 None、字符串或列表
        separator: 分隔符，默认为分号
    Returns:
        list: 处理后的列表
    """
    if value is None or value == "":
        return []
    elif isinstance(value, str):
        return [item.strip() for item in value.split(separator) if item.strip()]
    elif isinstance(value, list):
        return value
    return []


def check_ffmpeg_installed():
    ffmpeg_installed = False
    try:
        # 执行ffmpeg -version命令，并捕获输出
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,  # 如果返回码非零则抛出异常
        )
        # 检查输出中是否包含版本信息（可选）
        output = result.stdout + result.stderr
        if "ffmpeg version" in output.lower():
            ffmpeg_installed = True
        return False
    except (subprocess.CalledProcessError, FileNotFoundError):
        # 命令执行失败或未找到
        ffmpeg_installed = False
    if not ffmpeg_installed:
        error_msg = "您的电脑还没正确安装ffmpeg\n"
        error_msg += "\n建议您：\n"
        error_msg += "1、按照项目的安装文档，正确进入conda环境\n"
        error_msg += "2、查阅安装文档，如何在conda环境中安装ffmpeg\n"
        raise ValueError(error_msg)


def extract_json_from_string(input_string):
    """提取字符串中的 JSON 部分"""
    pattern = r"(\{.*\})"
    match = re.search(pattern, input_string, re.DOTALL)  # 添加 re.DOTALL
    if match:
        return match.group(1)  # 返回提取的 JSON 字符串
    return None


def analyze_emotion(text):
    """
    分析文本情感并返回对应的emoji名称（支持中英文）
    """
    if not text or not isinstance(text, str):
        return "neutral"

    original_text = text
    text = text.lower().strip()

    # 检查是否包含现有emoji
    for emotion, emoji in emoji_map.items():
        if emoji in original_text:
            return emotion

    # 标点符号分析
    has_exclamation = "!" in original_text or "！" in original_text
    has_question = "?" in original_text or "？" in original_text
    has_ellipsis = "..." in original_text or "…" in original_text

    # 定义情感关键词映射（中英文扩展版）
    emotion_keywords = {
        "happy": [
            "开心",
            "高兴",
            "快乐",
            "愉快",
            "幸福",
            "满意",
            "棒",
            "好",
            "不错",
            "完美",
            "棒极了",
            "太好了",
            "好呀",
            "好的",
            "happy",
            "joy",
            "great",
            "good",
            "nice",
            "awesome",
            "fantastic",
            "wonderful",
        ],
        "laughing": [
            "哈哈",
            "哈哈哈",
            "呵呵",
            "嘿嘿",
            "嘻嘻",
            "笑死",
            "太好笑了",
            "笑死我了",
            "lol",
            "lmao",
            "haha",
            "hahaha",
            "hehe",
            "rofl",
            "funny",
            "laugh",
        ],
        "funny": [
            "搞笑",
            "滑稽",
            "逗",
            "幽默",
            "笑点",
            "段子",
            "笑话",
            "太逗了",
            "hilarious",
            "joke",
            "comedy",
        ],
        "sad": [
            "伤心",
            "难过",
            "悲哀",
            "悲伤",
            "忧郁",
            "郁闷",
            "沮丧",
            "失望",
            "想哭",
            "难受",
            "不开心",
            "唉",
            "呜呜",
            "sad",
            "upset",
            "unhappy",
            "depressed",
            "sorrow",
            "gloomy",
        ],
        "angry": [
            "生气",
            "愤怒",
            "气死",
            "讨厌",
            "烦人",
            "可恶",
            "烦死了",
            "恼火",
            "暴躁",
            "火大",
            "愤怒",
            "气炸了",
            "angry",
            "mad",
            "annoyed",
            "furious",
            "pissed",
            "hate",
        ],
        "crying": [
            "哭泣",
            "泪流",
            "大哭",
            "伤心欲绝",
            "泪目",
            "流泪",
            "哭死",
            "哭晕",
            "想哭",
            "泪崩",
            "cry",
            "crying",
            "tears",
            "sob",
            "weep",
        ],
        "loving": [
            "爱你",
            "喜欢",
            "爱",
            "亲爱的",
            "宝贝",
            "么么哒",
            "抱抱",
            "想你",
            "思念",
            "最爱",
            "亲亲",
            "喜欢你",
            "love",
            "like",
            "adore",
            "darling",
            "sweetie",
            "honey",
            "miss you",
            "heart",
        ],
        "embarrassed": [
            "尴尬",
            "不好意思",
            "害羞",
            "脸红",
            "难为情",
            "社死",
            "丢脸",
            "出丑",
            "embarrassed",
            "awkward",
            "shy",
            "blush",
        ],
        "surprised": [
            "惊讶",
            "吃惊",
            "天啊",
            "哇塞",
            "哇",
            "居然",
            "竟然",
            "没想到",
            "出乎意料",
            "surprise",
            "wow",
            "omg",
            "oh my god",
            "amazing",
            "unbelievable",
        ],
        "shocked": [
            "震惊",
            "吓到",
            "惊呆了",
            "不敢相信",
            "震撼",
            "吓死",
            "恐怖",
            "害怕",
            "吓人",
            "shocked",
            "shocking",
            "scared",
            "frightened",
            "terrified",
            "horror",
        ],
        "thinking": [
            "思考",
            "考虑",
            "想一下",
            "琢磨",
            "沉思",
            "冥想",
            "想",
            "思考中",
            "在想",
            "think",
            "thinking",
            "consider",
            "ponder",
            "meditate",
        ],
        "winking": [
            "调皮",
            "眨眼",
            "你懂的",
            "坏笑",
            "邪恶",
            "奸笑",
            "使眼色",
            "wink",
            "teasing",
            "naughty",
            "mischievous",
        ],
        "cool": [
            "酷",
            "帅",
            "厉害",
            "棒极了",
            "真棒",
            "牛逼",
            "强",
            "优秀",
            "杰出",
            "出色",
            "完美",
            "cool",
            "awesome",
            "amazing",
            "great",
            "impressive",
            "perfect",
        ],
        "relaxed": [
            "放松",
            "舒服",
            "惬意",
            "悠闲",
            "轻松",
            "舒适",
            "安逸",
            "自在",
            "relax",
            "relaxed",
            "comfortable",
            "cozy",
            "chill",
            "peaceful",
        ],
        "delicious": [
            "好吃",
            "美味",
            "香",
            "馋",
            "可口",
            "香甜",
            "大餐",
            "大快朵颐",
            "流口水",
            "垂涎",
            "delicious",
            "yummy",
            "tasty",
            "yum",
            "appetizing",
            "mouthwatering",
        ],
        "kissy": [
            "亲亲",
            "么么",
            "吻",
            "mua",
            "muah",
            "亲一下",
            "飞吻",
            "kiss",
            "xoxo",
            "hug",
            "muah",
            "smooch",
        ],
        "confident": [
            "自信",
            "肯定",
            "确定",
            "毫无疑问",
            "当然",
            "必须的",
            "毫无疑问",
            "确信",
            "坚信",
            "confident",
            "sure",
            "certain",
            "definitely",
            "positive",
        ],
        "sleepy": [
            "困",
            "睡觉",
            "晚安",
            "想睡",
            "好累",
            "疲惫",
            "疲倦",
            "困了",
            "想休息",
            "睡意",
            "sleep",
            "sleepy",
            "tired",
            "exhausted",
            "bedtime",
            "good night",
        ],
        "silly": [
            "傻",
            "笨",
            "呆",
            "憨",
            "蠢",
            "二",
            "憨憨",
            "傻乎乎",
            "呆萌",
            "silly",
            "stupid",
            "dumb",
            "foolish",
            "goofy",
            "ridiculous",
        ],
        "confused": [
            "疑惑",
            "不明白",
            "不懂",
            "困惑",
            "疑问",
            "为什么",
            "怎么回事",
            "啥意思",
            "不清楚",
            "confused",
            "puzzled",
            "doubt",
            "question",
            "what",
            "why",
            "how",
        ],
    }

    # 特殊句型判断（中英文）
    # 赞美他人
    if any(
        phrase in text
        for phrase in [
            "你真",
            "你好",
            "您真",
            "你真棒",
            "你好厉害",
            "你太强了",
            "你真好",
            "你真聪明",
            "you are",
            "you're",
            "you look",
            "you seem",
            "so smart",
            "so kind",
        ]
    ):
        return "loving"
    # 自我赞美
    if any(
        phrase in text
        for phrase in [
            "我真",
            "我最",
            "我太棒了",
            "我厉害",
            "我聪明",
            "我优秀",
            "i am",
            "i'm",
            "i feel",
            "so good",
            "so happy",
        ]
    ):
        return "cool"
    # 晚安/睡觉相关
    if any(
        phrase in text
        for phrase in [
            "睡觉",
            "晚安",
            "睡了",
            "好梦",
            "休息了",
            "去睡了",
            "sleep",
            "good night",
            "bedtime",
            "go to bed",
        ]
    ):
        return "sleepy"
    # 疑问句
    if has_question and not has_exclamation:
        return "thinking"
    # 强烈情感（感叹号）
    if has_exclamation and not has_question:
        # 检查是否是积极内容
        positive_words = (
            emotion_keywords["happy"]
            + emotion_keywords["laughing"]
            + emotion_keywords["cool"]
        )
        if any(word in text for word in positive_words):
            return "laughing"
        # 检查是否是消极内容
        negative_words = (
            emotion_keywords["angry"]
            + emotion_keywords["sad"]
            + emotion_keywords["crying"]
        )
        if any(word in text for word in negative_words):
            return "angry"
        return "surprised"
    # 省略号（表示犹豫或思考）
    if has_ellipsis:
        return "thinking"

    # 关键词匹配（带权重）
    emotion_scores = {emotion: 0 for emotion in emoji_map.keys()}

    # 给匹配到的关键词加分
    for emotion, keywords in emotion_keywords.items():
        for keyword in keywords:
            if keyword in text:
                emotion_scores[emotion] += 1

    # 给长文本中的重复关键词额外加分
    if len(text) > 20:  # 长文本
        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                emotion_scores[emotion] += text.count(keyword) * 0.5

    # 根据分数选择最可能的情感
    max_score = max(emotion_scores.values())
    if max_score == 0:
        return "happy"  # 默认

    # 可能有多个情感同分，根据上下文选择最合适的
    top_emotions = [e for e, s in emotion_scores.items() if s == max_score]

    # 如果多个情感同分，使用以下优先级
    priority_order = [
        "laughing",
        "crying",
        "angry",
        "surprised",
        "shocked",  # 强烈情感优先
        "loving",
        "happy",
        "funny",
        "cool",  # 积极情感
        "sad",
        "embarrassed",
        "confused",  # 消极情感
        "thinking",
        "winking",
        "relaxed",  # 中性情感
        "delicious",
        "kissy",
        "confident",
        "sleepy",
        "silly",  # 特殊场景
    ]

    for emotion in priority_order:
        if emotion in top_emotions:
            return emotion

    return top_emotions[0]  # 如果都不在优先级列表里，返回第一个


def audio_to_data(audio_file_path, is_opus=True):
    # 获取文件后缀名
    file_type = os.path.splitext(audio_file_path)[1]
    if file_type:
        file_type = file_type.lstrip(".")
    # 读取音频文件，-nostdin 参数：不要从标准输入读取数据，否则FFmpeg会阻塞
    audio = AudioSegment.from_file(
        audio_file_path, format=file_type, parameters=["-nostdin"]
    )

    # 转换为单声道/16kHz采样率/16位小端编码（确保与编码器匹配）
    audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)

    # 音频时长(秒)
    duration = len(audio) / 1000.0

    # 获取原始PCM数据（16位小端）
    raw_data = audio.raw_data
    return pcm_to_data(raw_data, is_opus), duration


def audio_bytes_to_data(audio_bytes, file_type, is_opus=True):
    """
    直接用音频二进制数据转为opus/pcm数据，支持wav、mp3、p3
    """
    if file_type == "p3":
        # 直接用p3解码
        return p3.decode_opus_from_bytes(audio_bytes)
    else:
        # 其他格式用pydub
        audio = AudioSegment.from_file(BytesIO(audio_bytes), format=file_type, parameters=["-nostdin"])
        audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        duration = len(audio) / 1000.0
        raw_data = audio.raw_data
        return pcm_to_data(raw_data, is_opus), duration


def pcm_to_data(raw_data, is_opus=True):
    # 初始化Opus编码器
    encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)

    # 编码参数
    frame_duration = 60  # 60ms per frame
    frame_size = int(16000 * frame_duration / 1000)  # 960 samples/frame

    datas = []
    # 按帧处理所有音频数据（包括最后一帧可能补零）
    for i in range(0, len(raw_data), frame_size * 2):  # 16bit=2bytes/sample
        # 获取当前帧的二进制数据
        chunk = raw_data[i : i + frame_size * 2]

        # 如果最后一帧不足，补零
        if len(chunk) < frame_size * 2:
            chunk += b"\x00" * (frame_size * 2 - len(chunk))

        if is_opus:
            # 转换为numpy数组处理
            np_frame = np.frombuffer(chunk, dtype=np.int16)
            # 编码Opus数据
            frame_data = encoder.encode(np_frame.tobytes(), frame_size)
        else:
            frame_data = chunk if isinstance(chunk, bytes) else bytes(chunk)

        datas.append(frame_data)

    return datas


def opus_datas_to_wav_bytes(opus_datas, sample_rate=16000, channels=1):
    """
    将opus帧列表解码为wav字节流
    """
    decoder = opuslib_next.Decoder(sample_rate, channels)
    pcm_datas = []

    frame_duration = 60  # ms
    frame_size = int(sample_rate * frame_duration / 1000)  # 960

    for opus_frame in opus_datas:
        # 解码为PCM（返回bytes，2字节/采样点）
        pcm = decoder.decode(opus_frame, frame_size)
        pcm_datas.append(pcm)

    pcm_bytes = b''.join(pcm_datas)

    # 写入wav字节流
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return wav_buffer.getvalue()


def check_vad_update(before_config, new_config):
    if (
        new_config.get("selected_module") is None
        or new_config["selected_module"].get("VAD") is None
    ):
        return False
    update_vad = False
    current_vad_module = before_config["selected_module"]["VAD"]
    new_vad_module = new_config["selected_module"]["VAD"]
    current_vad_type = (
        current_vad_module
        if "type" not in before_config["VAD"][current_vad_module]
        else before_config["VAD"][current_vad_module]["type"]
    )
    new_vad_type = (
        new_vad_module
        if "type" not in new_config["VAD"][new_vad_module]
        else new_config["VAD"][new_vad_module]["type"]
    )
    update_vad = current_vad_type != new_vad_type
    return update_vad


def check_asr_update(before_config, new_config):
    if (
        new_config.get("selected_module") is None
        or new_config["selected_module"].get("ASR") is None
    ):
        return False
    update_asr = False
    current_asr_module = before_config["selected_module"]["ASR"]
    new_asr_module = new_config["selected_module"]["ASR"]
    current_asr_type = (
        current_asr_module
        if "type" not in before_config["ASR"][current_asr_module]
        else before_config["ASR"][current_asr_module]["type"]
    )
    new_asr_type = (
        new_asr_module
        if "type" not in new_config["ASR"][new_asr_module]
        else new_config["ASR"][new_asr_module]["type"]
    )
    update_asr = current_asr_type != new_asr_type
    return update_asr


def filter_sensitive_info(config: dict) -> dict:
    """
    过滤配置中的敏感信息
    Args:
        config: 原始配置字典
    Returns:
        过滤后的配置字典
    """
    sensitive_keys = [
        "api_key",
        "personal_access_token",
        "access_token",
        "token",
        "secret",
        "access_key_secret",
        "secret_key",
    ]

    def _filter_dict(d: dict) -> dict:
        filtered = {}
        for k, v in d.items():
            if any(sensitive in k.lower() for sensitive in sensitive_keys):
                filtered[k] = "***"
            elif isinstance(v, dict):
                filtered[k] = _filter_dict(v)
            elif isinstance(v, list):
                filtered[k] = [_filter_dict(i) if isinstance(i, dict) else i for i in v]
            else:
                filtered[k] = v
        return filtered

    return _filter_dict(copy.deepcopy(config))


def get_vision_url(config: dict) -> str:
    """获取 vision URL

    Args:
        config: 配置字典

    Returns:
        str: vision URL
    """
    server_config = config["server"]
    vision_explain = server_config.get("vision_explain", "")
    if "你的" in vision_explain:
        local_ip = get_local_ip()
        port = int(server_config.get("http_port", 8003))
        vision_explain = f"http://{local_ip}:{port}/mcp/vision/explain"
    return vision_explain


def is_valid_image_file(file_data: bytes) -> bool:
    """
    检查文件数据是否为有效的图片格式

    Args:
        file_data: 文件的二进制数据

    Returns:
        bool: 如果是有效的图片格式返回True，否则返回False
    """
    # 常见图片格式的魔数（文件头）
    image_signatures = {
        b"\xff\xd8\xff": "JPEG",
        b"\x89PNG\r\n\x1a\n": "PNG",
        b"GIF87a": "GIF",
        b"GIF89a": "GIF",
        b"BM": "BMP",
        b"II*\x00": "TIFF",
        b"MM\x00*": "TIFF",
        b"RIFF": "WEBP",
    }

    # 检查文件头是否匹配任何已知的图片格式
    for signature in image_signatures:
        if file_data.startswith(signature):
            return True

    return False


def sanitize_tool_name(name: str) -> str:
    """Sanitize tool names for OpenAI compatibility."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def get_location_display(lat, lon):
    """
    根据经纬度获取「城市+街道」描述，失败则返回原始经纬度字符串。

    :param lat: 纬度 (float 或 str)
    :param lon: 经度 (float 或 str)
    :param contact_email: 用于 User-Agent 的联系邮箱（请替换为你的真实邮箱）
    :return: str，例如 "北京市 东长安街" 或 "39.9042,116.4074"
    """
    # 构造 Nominatim 请求
    url = "https://nominatim.openstreetmap.org/reverse"
    headers = {
        'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
    }
    params = {
        'format': 'json',
        'lat': lat,
        'lon': lon,
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        # 注意：Nominatim 不返回标准 HTTP 错误码，即使没结果也是 200
        if response.status_code != 200:
            return f"{lat},{lon}"

        data = response.json()

        # 检查是否包含有效地址
        if 'error' in data or not data.get('address'):
            return f"{lat},{lon}"

        addr = data['address']

        # 尝试提取城市：优先 city，其次 town/village
        city = (
                addr.get('city') or
                addr.get('town') or
                addr.get('village') or
                addr.get('county') or
                addr.get('state') or
                ''
        )

        # 提取街道信息
        road = addr.get('road', '')
        house_number = addr.get('house_number', '')

        # 组合街道（如有门牌号）
        street = f"{house_number} {road}".strip() if house_number else road

        # 如果有城市和街道，返回组合；否则尽量返回可用信息
        if city and street:
            return f"{city} {street}"
        elif city:
            return city
        elif street:
            return street
        else:
            return f"{lat},{lon}"

    except Exception as e:
        # 任何异常（网络、解析、超时等）都回退到经纬度
        print(f"[警告] Nominatim 调用失败: {e}")
        return f"{lat},{lon}"
