import requests
from bs4 import BeautifulSoup
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from core.utils.util import get_ip_info

TAG = __name__
logger = setup_logging()

GET_WEATHER_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "获取某个地点的天气，用户应提供一个位置，比如用户说杭州天气，参数为：杭州;"
            "如果用户说的是省份，默认用省会城市。如果用户说的不是省份或城市而是一个地名，默认用该地所在省份的省会城市。"
            "如果用户没有指明地点，说“天气怎么样”，”今天天气如何“，location参数为空。"
            "返回结果中请添加贴心的当前天气个性化建议。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "地点名，例如杭州。可选参数，如果不提供则不传",
                },
                "lang": {
                    "type": "string",
                    "description": "返回用户使用的语言code，例如zh_CN/zh_HK/en_US/ja_JP等，默认zh_CN",
                },
            },
            "required": ["lang"],
        },
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
    )
}

# 天气代码 https://dev.qweather.com/docs/resource/icons/#weather-icons
WEATHER_CODE_MAP = {
    "100": "晴",
    "101": "多云",
    "102": "少云",
    "103": "晴间多云",
    "104": "阴",
    "150": "晴",
    "151": "多云",
    "152": "少云",
    "153": "晴间多云",
    "300": "阵雨",
    "301": "强阵雨",
    "302": "雷阵雨",
    "303": "强雷阵雨",
    "304": "雷阵雨伴有冰雹",
    "305": "小雨",
    "306": "中雨",
    "307": "大雨",
    "308": "极端降雨",
    "309": "毛毛雨/细雨",
    "310": "暴雨",
    "311": "大暴雨",
    "312": "特大暴雨",
    "313": "冻雨",
    "314": "小到中雨",
    "315": "中到大雨",
    "316": "大到暴雨",
    "317": "暴雨到大暴雨",
    "318": "大暴雨到特大暴雨",
    "350": "阵雨",
    "351": "强阵雨",
    "399": "雨",
    "400": "小雪",
    "401": "中雪",
    "402": "大雪",
    "403": "暴雪",
    "404": "雨夹雪",
    "405": "雨雪天气",
    "406": "阵雨夹雪",
    "407": "阵雪",
    "408": "小到中雪",
    "409": "中到大雪",
    "410": "大到暴雪",
    "456": "阵雨夹雪",
    "457": "阵雪",
    "499": "雪",
    "500": "薄雾",
    "501": "雾",
    "502": "霾",
    "503": "扬沙",
    "504": "浮尘",
    "507": "沙尘暴",
    "508": "强沙尘暴",
    "509": "浓雾",
    "510": "强浓雾",
    "511": "中度霾",
    "512": "重度霾",
    "513": "严重霾",
    "514": "大雾",
    "515": "特强浓雾",
    "900": "热",
    "901": "冷",
    "999": "未知",
}


def fetch_city_info(location, api_key, api_host):
    url = f"https://{api_host}/geo/v2/city/lookup?key={api_key}&location={location}&lang=zh"
    response = requests.get(url, headers=HEADERS).json()
    return response.get("location", [])[0] if response.get("location") else None


def fetch_weather_page(url):
    response = requests.get(url, headers=HEADERS)
    return BeautifulSoup(response.text, "html.parser") if response.ok else None


def parse_weather_info(soup):
    city_name = soup.select_one("h1.c-submenu__location").get_text(strip=True)

    current_abstract = soup.select_one(".c-city-weather-current .current-abstract")
    current_abstract = (
        current_abstract.get_text(strip=True) if current_abstract else "未知"
    )

    current_basic = {}
    for item in soup.select(
        ".c-city-weather-current .current-basic .current-basic___item"
    ):
        parts = item.get_text(strip=True, separator=" ").split(" ")
        if len(parts) == 2:
            key, value = parts[1], parts[0]
            current_basic[key] = value

    temps_list = []
    for row in soup.select(".city-forecast-tabs__row")[:7]:  # 取前7天的数据
        date = row.select_one(".date-bg .date").get_text(strip=True)
        weather_code = (
            row.select_one(".date-bg .icon")["src"].split("/")[-1].split(".")[0]
        )
        weather = WEATHER_CODE_MAP.get(weather_code, "未知")
        temps = [span.get_text(strip=True) for span in row.select(".tmp-cont .temp")]
        high_temp, low_temp = (temps[0], temps[-1]) if len(temps) >= 2 else (None, None)
        temps_list.append((date, weather, high_temp, low_temp))

    return city_name, current_abstract, current_basic, temps_list


# 天气描述映射
def get_weather_description(weather_main, weather_description):
    # 简单的英文天气描述到中文的映射
    weather_map = {
        "Clear": "晴",
        "Clouds": "云",
        "Rain": "雨",
        "Snow": "雪",
        "Thunderstorm": "雷暴",
        "Drizzle": "毛毛雨",
        "Mist": "薄雾",
        "Fog": "雾",
        "Haze": "霾"
    }
    
    # 详细描述映射
    description_map = {
        "sky is clear": "晴朗",
        "few clouds": "少云",
        "scattered clouds": "多云",
        "broken clouds": "阴云",
        "overcast clouds": "阴天",
        "light rain": "小雨",
        "moderate rain": "中雨",
        "heavy intensity rain": "大雨",
        "very heavy rain": "暴雨"
    }
    
    main_cn = weather_map.get(weather_main, weather_main)
    desc_cn = description_map.get(weather_description.lower(), weather_description)
    
    return f"{main_cn}{desc_cn}"


api_host = "pq5vxm8qxh.re.qweatherapi.com"
api_key = "3ad97c63375a4911ab3c655a375c126b"
default_lat = 22.57
default_lon = 113.85
default_location = "深圳"


@register_function("get_weather", GET_WEATHER_FUNCTION_DESC, ToolType.SYSTEM_CTL)
def get_weather(conn, location: str = None, lang: str = "zh_CN"):

    from core.utils.cache.manager import cache_manager, CacheType

    print(f"进入天气插件: {location}_{lang}")

    # 尝试从缓存获取天气（使用经纬度作为缓存键的一部分）
    weather_cache_key = f"full_weather_{location}_{lang}"
    cached_weather_report = cache_manager.get(CacheType.WEATHER, weather_cache_key)

    final_lat = default_lat
    final_lon = default_lon

    # 优先使用用户提供的location参数
    if location is None:
        location = f"{conn.lon},{conn.lat}"
        final_lat = conn.lat
        final_lon = conn.lon
        final_location = default_location

    #判断如果是尝试名称，则进行解析
    if ',' not in location:
        city_info = fetch_city_info(location, api_key, api_host)
        if not city_info:
            return ActionResponse(
                Action.REQLLM, f"未找到相关的城市: {location}，请确认地点是否正确", None
            )
        final_lat = city_info["lat"]
        final_lon = city_info["lon"]
        final_location = city_info["name"]

    logger.info(f"请求天气经纬度: {final_lat}, {final_lon}")

    logger.info(f"天气插件请求缓存数据：{cached_weather_report}")

    if cached_weather_report:
        logger.info(f"从缓存中获取天气: {weather_cache_key}")
        return ActionResponse(Action.REQLLM, cached_weather_report, None)

    try:
        # 调用新的天气API
        api_url = "https://api.iot-solution.net/kotlinweb/weather_info/forecast"
        form_data = {
            "projectId": "84",
            "lat": final_lat,
            "lon": final_lon
        }
        
        logger.info(f"调用天气API: {api_url}, 参数: {form_data}")
        response = requests.post(api_url, data=form_data, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"API请求失败，状态码: {response.status_code}, 响应: {response.text}")
            return ActionResponse(Action.REQLLM, None, "天气API请求失败，请稍后再试")
        
        weather_data = response.json()
        logger.info(f"天气API响应数据: {weather_data}")
        
        if weather_data.get("code") != 0:
            return ActionResponse(Action.REQLLM, None, f"获取天气失败: {weather_data.get('mesg', '未知错误')}")
        
        forecast_data = weather_data.get("data", [])
        if not forecast_data:
            return ActionResponse(Action.REQLLM, None, "未获取到天气数据")
        
        # 获取当前天气（第一天数据）
        current_weather = forecast_data[0]
        # city_name = current_weather.get("name", "未知位置")
        
        # 构建天气报告
        weather_report = f"您当前的位置是：{final_location}\n\n"
        
        # 当前天气信息
        weather_main = current_weather.get("weather_main", "")
        weather_description = current_weather.get("weather_description", "")
        temp_day = current_weather.get("temp_day", "")
        feels_like_day = current_weather.get("feels_like_day", "")
        humidity = current_weather.get("humidity", "")
        wind_speed = current_weather.get("wind_speed", "")
        
        weather_desc = get_weather_description(weather_main, weather_description)
        weather_report += f"当前天气: {weather_desc}\n"
        weather_report += f"当前温度: {temp_day}°C，体感温度: {feels_like_day}°C\n"
        
        # 详细参数
        weather_report += "详细参数：\n"
        weather_report += f"  · 湿度: {humidity}%\n"
        weather_report += f"  · 风速: {wind_speed} m/s\n"
        weather_report += f"  · 气压: {current_weather.get('pressure', '')} hPa\n"
        weather_report += f"  · 云量: {current_weather.get('clouds_all', '')}%\n"
        weather_report += f"  · 紫外线指数: {current_weather.get('uvi', '')}\n"
        
        # 日出日落信息
        sunrise = current_weather.get("sys_sunrise_read", "")
        sunset = current_weather.get("sys_sunset_read", "")
        if sunrise and sunset:
            weather_report += f"  · 日出: {sunrise.split(' ')[1]}\n"
            weather_report += f"  · 日落: {sunset.split(' ')[1]}\n"
        
        # 添加7天预报
        weather_report += "\n未来7天预报：\n"
        for day in forecast_data[:7]:  # 取前7天的数据
            date = day.get("dt_read", "").split(' ')[0]  # 只取日期部分
            weather_main = day.get("weather_main", "")
            weather_description = day.get("weather_description", "")
            high_temp = day.get("temp_max", "")
            low_temp = day.get("temp_min", "")
            
            weather_desc = get_weather_description(weather_main, weather_description)
            weather_report += f"{date}: {weather_desc}，气温 {low_temp}~{high_temp}°C\n"
        
        # 提示语
        weather_report += "\n（如需某一天的具体天气，请告诉我日期）"
        weather_report += "\n你回复时必须说明用户的查询的位置名称，并且回复最后添加贴心的当前天气的建议。"
        
        # 缓存完整的天气报告
        cache_manager.set(CacheType.WEATHER, weather_cache_key, weather_report)
        
        return ActionResponse(Action.REQLLM, weather_report, None)

    except Exception as e:
        logger.error(f"获取天气信息时发生错误: {e}", exc_info=True)
        return ActionResponse(Action.REQLLM, None, "获取天气信息异常，请稍后再试")
