import json
import logging
import os
from typing import Dict, List, Optional
import requests
from pydantic import BaseModel

from plugins_func.register import register_function, ToolType, ActionResponse, Action

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
使用Bocha Web Search API进行网页搜索的Python工具类
"""

api_key = "sk-886f31d498b54053b78ae5a862179f70"
base_url = "https://api.bochaai.com/v1/web-search"

GET_WEB_SEARCH_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_web_search",
        "description": (
            """
            使用网络搜索API搜索网页。返回搜索结果包括网页标题、网页URL、网页摘要、网站名称、网站图标、网页发布时间等。
            """
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用户提问的问题",
                }
            },
            "required": ["query"],
        },
    },
}


@register_function("get_web_search", GET_WEB_SEARCH_FUNCTION_DESC, ToolType.WAIT)
def get_web_search(query: str) -> str:
    """
    使用Bocha Web Search API进行网页搜索

    Args:
        query: 搜索关键词

    Returns:
        搜索结果的详细信息，包括网页标题、网页URL、网页摘要等
    """
    logger.info(f"开始搜索...{query}")
    return bocha_web_search_tool_extended(query, "noLimit", True, 10)


def bocha_web_search_tool_extended(query: str,
                                   freshness: str = "noLimit",
                                   summary: bool = True,
                                   count: int = 10) -> str:
    """
    使用Bocha Web Search API进行网页搜索（扩展版本）

    Args:
        query: 搜索关键词
        freshness: 搜索的时间范围
        summary: 是否显示文本摘要
        count: 返回的搜索结果数量

    Returns:
        搜索结果的详细信息，包括网页标题、网页URL、网页摘要、网站名称、网站Icon、网页发布时间等
    """
    # 设置请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 创建请求体
    request_body = {
        "query": query,
        "freshness": freshness,
        "summary": summary,
        "count": count
    }

    try:
        # 发送POST请求
        response = requests.post(
            base_url,
            headers=headers,
            json=request_body,
            timeout=30  # 设置超时时间
        )

        if response.status_code == 200:
            json_response = response.json()

            if json_response.get("code") != 200 or "data" not in json_response:
                error_msg = json_response.get("msg", "未知错误")
                logger.error(f"bocha_web_search_tool error: {error_msg}")
                return f"搜索API请求失败，原因是: {error_msg}"

            data = json_response["data"]
            if "webPages" not in data or "value" not in data["webPages"]:
                logger.error("bocha_web_search_tool error: 未找到相关结果")
                return "未找到相关结果。"

            webpages = data["webPages"]["value"]
            if not webpages:
                logger.error("bocha_web_search_tool error: 未找到相关结果")
                return "未找到相关结果。"

            formatted_results = []
            for idx, page in enumerate(webpages, 1):
                formatted_result = (
                    f"引用: {idx}\n"
                    f"标题: {page.get('name', '')}\n"
                    f"URL: {page.get('url', '')}\n"
                    f"摘要: {page.get('summary', '')}\n"
                    f"网站名称: {page.get('siteName', '')}\n"
                    f"网站图标: {page.get('siteIcon', '')}\n"
                    f"发布时间: {page.get('dateLastCrawled', '')}\n"
                )
                formatted_results.append(formatted_result)

            result_str = "\n".join(formatted_results)
            logger.info(f"搜索结果: {result_str}")

            return ActionResponse(Action.REQLLM, result_str.strip(), None)
        else:
            logger.error(f"bocha_web_search_tool error: {response.status_code}")
            return ActionResponse(Action.ERROR, "error", "error")

    except requests.exceptions.RequestException as e:
        logger.error(f"bocha_web_search_tool network error: {e}")
        return ActionResponse(Action.ERROR, "error", "error")
    except json.JSONDecodeError as e:
        logger.error(f"bocha_web_search_tool JSON parse error: {e}")
        return ActionResponse(Action.ERROR, "error", "error")
    except Exception as e:
        logger.error(f"bocha_web_search_tool unexpected error: {e}")
        return ActionResponse(Action.ERROR, "error", "error")


# 以下是使用示例和工具函数
class SearchResult(BaseModel):
    """搜索结果数据模型"""
    title: str
    url: str
    summary: str
    site_name: str
    site_icon: str
    publish_time: str


def parse_search_results(search_output: str) -> List[SearchResult]:
    """
    解析搜索工具返回的字符串格式结果

    Args:
        search_output: 搜索工具返回的字符串

    Returns:
        解析后的搜索结果列表
    """
    results = []
    current_result = {}

    for line in search_output.split('\n'):
        if line.startswith('引用:'):
            if current_result:
                results.append(SearchResult(**current_result))
                current_result = {}
        elif line.startswith('标题:'):
            current_result['title'] = line[3:].strip()
        elif line.startswith('URL:'):
            current_result['url'] = line[4:].strip()
        elif line.startswith('摘要:'):
            current_result['summary'] = line[3:].strip()
        elif line.startswith('网站名称:'):
            current_result['site_name'] = line[5:].strip()
        elif line.startswith('网站图标:'):
            current_result['site_icon'] = line[5:].strip()
        elif line.startswith('发布时间:'):
            current_result['publish_time'] = line[5:].strip()

    if current_result:
        results.append(SearchResult(**current_result))

    return results


# 使用示例
if __name__ == "__main__":

    # 执行搜索
    query = "Python编程教程"
    result = bocha_web_search_tool(query)

    print("搜索完成，结果:")
    print(result)

    # 解析结果
    parsed_results = parse_search_results(result)
    for res in parsed_results:
        print(f"标题: {res.title}")
        print(f"URL: {res.url}")
        print("---")
