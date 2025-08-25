from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
import requests

logger = setup_logging()

get_periphery_function_desc = {
    "type": "function",
    "function": {
        "name": "get_periphery",
        "description": (
            "只有在用户明确提出“周边搜索”相关的问题时，才允许调用此工具函数。"
            "用户的表达通常包含关键词：附近、周边、哪里有、推荐、去哪里、想找、有什么好吃/好玩的。"
            "如果用户仅仅输入一个城市、地名、地址（如：北京、上海、天安门、世界之窗）、路线规划，不要触发此工具。"
            "如果用户问天气、新闻、聊天、知识问答、路线等内容，也不要触发此工具。"
            "工具功能：用于获取某个地点的周边美食或者好玩的地方。"
            "根据用户的提问进行分类，有："
            "美食，中餐，法餐，粤菜，生活服务，公园，公共厕所，图书馆，美术馆，汽车服务，加油站，汽车维修，购物服务，医疗保健服务，住宿服务,"
            "交通设施服务,汽车养护/装饰,充电站,换电站,娱乐场所,火车站,学校,住宅区,国家级景点,寺庙道观,海滩,动物园,休闲场所,银行,"
            "运动场所,足球场,游泳馆,健身中心,网球场,KTV,酒吧,夜总会,娱乐场所,游乐场,电影院,宾馆酒店,火锅店,潮州菜,日本料理,等等。"
            "比如用户说附近好吃的粤菜，则可以分到粤菜小类别，或者美食大类。"
            "比如用户说附近好玩的，可以分到风景名胜这个大类，或者公园这种小类。"
            "比如用户说附近的加油站，可以分到加油站这种小类。"
            "优先匹配小类，没有在匹配大类"
        ),
        "parameters": {
            "query": "用户询问的问题",
            "type": "用户的问题分类"
        },
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
    )
}



def fetch_city_info(location, api_key, api_host):
    url = f"https://{api_host}/geo/v2/city/lookup?key={api_key}&location={location}&lang=zh"
    response = requests.get(url, headers=HEADERS).json()
    return response.get("location", [])[0] if response.get("location") else None

def format_poi_for_model(poi_response: dict, user_location: str = None, query: str = "美食", max_items=5):
    """
    将高德地图 POI JSON 转成自然语言描述给模型
    """
    pois = poi_response.get("pois", [])[:max_items]
    if not pois:
        return f"未找到您附近的{query}。"

    # 用户当前地址
    location_text = f"你当前所在地址是 {user_location}" if user_location else ""

    # POI描述
    poi_texts = []
    for poi in pois:
        name = poi.get("name", "未知")
        address = poi.get("address", "无详细地址")
        poi_texts.append(f"{name}，地址在{address}")

    poi_text = "；\n".join(poi_texts)

    return f"{location_text}\n：\n{poi_text}。"

@register_function("get_periphery", get_periphery_function_desc, ToolType.SYSTEM_CTL)
def get_periphery(conn, query: str = None,type: str = None):

    api_host = "pq5vxm8qxh.re.qweatherapi.com"
    api_key = "3ad97c63375a4911ab3c655a375c126b"
    mapKey = conn.config["plugins"]["get_periphery"].get("mapKey", "a68d399ba21b8a0907bb68db22a426f7")
    print(f"进入查询周边工具：{type},mapKey={mapKey}")
    # default_location = "default_location"
    # client_ip = conn.client_ip
    # location = None
    if conn.lon and conn.lat:
        location = f"{conn.lon},{conn.lat}"
    else :
        return ActionResponse(
            Action.REQLLM, f"未找到您所在的位置，请确认是否打开位置信息", None
        )
    # elif client_ip:
    #     # 通过客户端IP解析城市
    #     # 动态解析IP对应的城市信息
    #     ip_info = get_ip_info(client_ip, logger)
    #     location = ip_info.get("city") if ip_info and "city" in ip_info else None
    city_info = fetch_city_info(location, api_key, api_host)
    print(f"city_info:{city_info}")
    if not city_info:
        return ActionResponse(
            Action.REQLLM, f"未找到相关的城市: {location}，请确认地点是否正确", None
        )
    user_location = city_info.get("name")  # 例如城市名
    mapUrl = f"https://restapi.amap.com/v5/place/text?key={mapKey}&city_limit=true&page_size=5&keywords={type}&region={user_location}&location={location}"
    response = requests.get(mapUrl, headers=HEADERS).json()
    model_input_text = format_poi_for_model(response, user_location=user_location, query=query)
    return ActionResponse(Action.REQLLM, model_input_text, None)
