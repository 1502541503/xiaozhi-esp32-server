from config.logger import setup_logging
from http import HTTPStatus
from dashscope import Application
from core.providers.llm.base import LLMProviderBase
from core.utils.util import check_model_key

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        print("图像识别 AliBL：", "111")
        self.provider = config.get("type", "AliBL")
        self.api_key = config["api_key"]
        self.app_id = config["app_id"]
        self.base_url = config.get("base_url")
        self.is_No_prompt = config.get("is_no_prompt")
        self.memory_id = config.get("ali_memory_id")
        check_model_key("AliBLLLM", self.api_key)

    def response(self, session_id, dialogue, imgurl=None):
        self.is_No_prompt = True
        print(f"response AliBL：{dialogue}")
        try:
            #处理上下文
            recent_dialogue = []
            for msg in reversed(dialogue):
                if msg.get("role") in ("user", "assistant"):
                    recent_dialogue.insert(0, msg)
                    if len(recent_dialogue) == 4:  # 两轮 = 4 条（user + assistant）× 2
                        break
            dialogue = recent_dialogue

            print(f"初始化后response AliBL：{dialogue}")

            # 处理dialogue
            # if self.is_No_prompt:
            #     dialogue.pop(0)
            #     logger.bind(tag=TAG).debug(
            #         f"【阿里百练API服务】处理后的dialogue: {dialogue}"
            #     )

            # 构造调用参数
            call_params = {
                "api_key": self.api_key,
                "app_id": self.app_id,
                "session_id": session_id,
                "messages": dialogue,
                "stream": True,
                "flow_stream_mode": "agent_format",  # 或 "full_thoughts"
                "incremental_output": True,
            }

            domain_mapping = {
                "https://dev-oss.iot-solution.net": "https://sma-hk-test.oss-accelerate.aliyuncs.com",
                "https://test-oss.iot-solution.net": "https://sma-test.oss-accelerate.aliyuncs.com",
                "https://api-oss.iot-solution.net": "https://sma-product.oss-accelerate.aliyuncs.com",
                "https://coding-eu-oss.iot-solution.net": "https://coding-eu.oss-accelerate.aliyuncs.com",
                "https://coding-shenzhen-oss.iot-solution.net": "https://coding-shenzhen.oss-accelerate.aliyuncs.com",
                "https://coding-usa-oss.iot-solution.net": "https://coding-usa.oss-accelerate.aliyuncs.com"
            }

            # 如果传入图片 URL，则包装成列表传给 image_list
            if imgurl:
                for old_domain, new_domain in domain_mapping.items():
                    if imgurl.startswith(old_domain):
                        imgurl = imgurl.replace(old_domain, new_domain, 1)
                        break  # 找到就替换，无需再判断后面的

                logger.bind(tag=TAG).info(
                    f"【阿里百练API服务】附加图片链接: {imgurl}"
                )

                call_params["image_list"] = [imgurl]

            # if self.memory_id != False:
            #     # 百练memory需要prompt参数
            #     print(f"进入配置prompt参数：{dialogue}")
            #     prompt = dialogue[-1].get("content")
            #     call_params["memory_id"] = self.memory_id
            #     call_params["prompt"] = prompt
            #     logger.bind(tag=TAG).debug(
            #         f"【阿里百练API服务】处理后的prompt: {prompt}"
            #     )

            stream_responses = Application.call(**call_params)

            for res in stream_responses:
                if res.status_code != HTTPStatus.OK:
                    logger.bind(tag=TAG).error(
                        f"【阿里百练API服务异常】code={res.status_code}, message={res.message}, request_id={res.request_id}"
                    )
                    yield f"【阿里百练API服务响应异常】{res.message}"
                    break
                else:
                    content = res.output.text or None
                    if content is not None:
                        logger.bind(tag=TAG).info(f"【阿里百练API服务】====: {content}")
                        yield content


        except Exception as e:
            logger.bind(tag=TAG).error(f"【阿里百练API服务】响应异常: {e}")
            yield "【LLM服务响应异常】"

    def response_with_functions(self, session_id, dialogue, functions=None):
        logger.bind(tag=TAG).error(
            f"阿里百练暂未实现完整的工具调用（function call），建议使用其他意图识别"
        )