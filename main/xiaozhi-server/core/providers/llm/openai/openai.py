import openai
from openai.types import CompletionUsage
from config.logger import setup_logging
from core.utils.util import check_model_key
from core.providers.llm.base import LLMProviderBase

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    def __init__(self, config):

        print("图像识别 openai：", "111")

        self.model_name = config.get("model_name")
        self.api_key = config.get("api_key")
        if "base_url" in config:
            self.base_url = config.get("base_url")
        else:
            self.base_url = config.get("url")

        param_defaults = {
            "max_tokens": (500, int),
            "temperature": (0.7, lambda x: round(float(x), 1)),
            "top_p": (1.0, lambda x: round(float(x), 1)),
            "frequency_penalty": (0, lambda x: round(float(x), 1))
        }

        for param, (default, converter) in param_defaults.items():
            value = config.get(param)
            try:
                setattr(self, param, converter(value) if value not in (None, "") else default)
            except (ValueError, TypeError):
                setattr(self, param, default)

        logger.debug(
            f"意图识别参数初始化: {self.temperature}, {self.max_tokens}, {self.top_p}, {self.frequency_penalty}")

        check_model_key("LLM", self.api_key)

        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers={
                "api-key": self.api_key
            }
        )

        self.default_vllm_user_msg = "请描述我眼前的画面，包括场景、主要物体、文字和可能的品牌信息。"
        self.vllm_system_prompt = """
        你是一个专为智能眼镜设计的实时视觉识别助手。
        你的任务是通过眼镜摄像头获取用户眼前的实时画面，进行快速、精准、简洁的环境理解，并通过语音向用户播报最关键的信息。
        回答必须**极其简洁**，控制在1-2句话内，适合语音播报。
           
        示例输出：
        - “你正站在一个明亮的办公室里，画面中有一些办公物品，电脑、键盘，鼠标等。”
        - “门上贴着一张便条，写着‘快递已取’。”   
        - “你面前是一瓶东方树叶青柑普洱茶饮料，净含量900ml，背景中有一个键盘和一些黄色小鸭子装饰”   
        
        """

    def response(self, session_id, dialogue, **kwargs):
        print(f"response openai：{dialogue}")
        print(f"response openai：{self.model_name}")
        print(f"response openai：{self.max_tokens}")
        try:
            responses = self.client.chat.completions.create(
                model=self.model_name,
                messages=dialogue,
                stream=True,
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                # temperature=kwargs.get("temperature", self.temperature),
                temperature=0.7,
                # top_p=kwargs.get("top_p", self.top_p),
                top_p=1.0,
                # frequency_penalty=kwargs.get("frequency_penalty", self.frequency_penalty),
            )

            is_active = True
            for chunk in responses:
                try:
                    # 检查是否存在有效的choice且content不为空
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    content = delta.content if hasattr(delta, "content") else ""
                except IndexError:
                    content = ""
                if content:
                    # 处理标签跨多个chunk的情况
                    if "<think>" in content:
                        is_active = False
                        content = content.split("<think>")[0]
                    if "</think>" in content:
                        is_active = True
                        content = content.split("</think>")[-1]
                    if is_active:
                        yield content

        except Exception as e:
            logger.bind(tag=TAG).error(f"Error in response generation: {e}")

    def response_with_functions(self, session_id, dialogue, functions=None, imgUrl=None):
        try:
            domain_mapping = {
                "https://dev-oss.iot-solution.net": "https://sma-hk-test.oss-accelerate.aliyuncs.com",
                "https://test-oss.iot-solution.net": "https://sma-test.oss-accelerate.aliyuncs.com",
                "https://api-oss.iot-solution.net": "https://sma-product.oss-accelerate.aliyuncs.com",
                "https://coding-eu-oss.iot-solution.net": "https://coding-eu.oss-accelerate.aliyuncs.com",
                "https://coding-shenzhen-oss.iot-solution.net": "https://coding-shenzhen.oss-accelerate.aliyuncs.com",
                "https://coding-usa-oss.iot-solution.net": "https://coding-usa.oss-accelerate.aliyuncs.com"
            }
            model_name = self.model_name
            if imgUrl:
                for old_domain, new_domain in domain_mapping.items():
                    if imgUrl.startswith(old_domain):
                        imgUrl = imgUrl.replace(old_domain, new_domain, 1)
                        break  # 找到就替换，无需再判断后面的

            logger.bind(tag=TAG).info(f"response_with_functions imgUrl: {imgUrl},modelname:{model_name}")
            logger.bind(tag=TAG).info(f"dialogue: {dialogue}")

            if imgUrl:

                logger.bind(tag=TAG).info(f"开始图片识别=>")

                model_name = "qwen-vl-plus"

                # 提取最后的用户消息内容
                original_text = ""
                for i in range(len(dialogue) - 1, -1, -1):
                    if dialogue[i].get("role") == "user":
                        original_text = dialogue[i].get("content", "")
                        if not original_text or not original_text.strip():
                            original_text = self.default_vllm_user_msg  # 默认文本
                        break

                # 构建视觉识别的完整对话
                dialogue = [
                    {
                        "role": "system",
                        "content": self.vllm_system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": original_text},
                            {"type": "image_url", "image_url": {"url": imgUrl}}
                        ]
                    }
                ]

            logger.bind(tag=TAG).info(f"response_with_functions: {dialogue}")

            stream = self.client.chat.completions.create(
                model=model_name, messages=dialogue, stream=True, tools=functions
            )

            for chunk in stream:
                # 检查是否存在有效的choice且content不为空
                if getattr(chunk, "choices", None):
                    yield chunk.choices[0].delta.content, chunk.choices[0].delta.tool_calls
                # 存在 CompletionUsage 消息时，生成 Token 消耗 log
                elif isinstance(getattr(chunk, 'usage', None), CompletionUsage):
                    usage_info = getattr(chunk, 'usage', None)
                    logger.bind(tag=TAG).info(
                        f"Token 消耗：输入 {getattr(usage_info, 'prompt_tokens', '未知')}，"
                        f"输出 {getattr(usage_info, 'completion_tokens', '未知')}，"
                        f"共计 {getattr(usage_info, 'total_tokens', '未知')}"
                    )

        except Exception as e:
            logger.bind(tag=TAG).error(f"问答异常: {e}")
            yield f"【抱歉，服务器开小差，请再次尝试】", None
