import logging
from typing import Optional

import requests
import json

from config import config

logger = logging.getLogger(__name__)

class BusApi:
    def __init__(self):
        # API endpoints
        self.cityList = config.get("api_endpoint", "cityList")
        self.homePageInfo = config.get("api_endpoint", "homePageInfo")
        self.lineDetail = config.get("api_endpoint", "lineDetail")
        self.busesDetail = config.get("api_endpoint", "busesDetail")
        self.getBusTime = config.get("api_endpoint", "getBusTime")
        # Required parameters
        self.gps_type = config.get("api_parameters", "gpstype", "wgs")
        self.s = config.get("api_parameters", "s")
        self.v = config.get("api_parameters", "v")
        self.src = config.get("api_parameters", "src")
        self.userId = config.get("api_parameters", "userId")
        self.sign = config.get("api_parameters", "sign")

        self.city_id = config.get("location", "cityId")
        self.lat = config.get("location", "lat")
        self.lng = config.get("location", "lng")
        self.wgs_lat = config.get("location", "wgsLat")
        self.wgs_lng = config.get("location", "wgsLng")

    @staticmethod
    def curl_request(url, method="GET", data=None, headers=None):
        try:
            if method == "POST":
                response = requests.post(url, data=data, headers=headers, timeout=10)
            else:
                response = requests.get(url, params=data, headers=headers, timeout=10)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None

    def get_city(self, gps_type: str = None, lat: str = None, lng: str = None) -> Optional[dict]:
        """
        获取城市信息
        :param gps_type: 坐标类型
        :param lat: 纬度
        :param lng: 经度
        """
        params = {
            "type": "gpsRealtimeCity",
            "lat": lat if lat else self.wgs_lat,
            "lng": lng if lng else self.wgs_lng,
            "gpstype": gps_type if gps_type else self.gps_type,
            "s": self.s,
            "v": self.v,
            "src": self.src,
            "userId": self.userId,
        }
        response = self.curl_request(self.cityList, method="POST", data=params)
        if response:
            json_data = response.json()
            if json_data.get("status") == "OK":
                return json_data["data"].get("gpsRealtimeCity")
        return None

    @staticmethod
    def replace_response_special_chars(string) -> str:
        """
        替换响应中的特殊字符
        :param string: 字符串
        """
        return string.replace("YGKJ##", "").replace("**YGKJ", "")

    def get_arr(self, city_id: str = None, gps_type: str = None, lat: str = None, lng: str = None) -> Optional[dict]:
        """
        获取附近站点的线路及信息
        :param city_id: city id from get_city method
        :param gps_type: 坐标类型
        :param lat:     纬度
        :param lng:     经度
        """
        params = {
            "gpstype": gps_type if gps_type else self.gps_type,
            "cityId": city_id if city_id else self.city_id,
            "lat": lat if lat else self.wgs_lat,
            "lng": lng if lng else self.wgs_lng,
            "type": 1,
            "act": 2,
            "gpsAccuracy": 65.0,
            "hist": "",
            "dpi": 3,
            "push_open": 1,
            "sign": self.sign,
            "s": self.s,
            "v": self.v,
        }
        response = self.curl_request(self.homePageInfo, data=params)
        if response:
            data = self.replace_response_special_chars(response.text)
            json_data = json.loads(data)
            if json_data.get("jsonr", {}).get("status") == "00":
                return json_data["jsonr"]["data"]
        return None

    def get_line_detail(self, line_id: str, target_order: str = None, city_id: str = None,
                        lat: str = None, lng: str = None) -> Optional[dict]:
        """
        获取公交车实时信息
        :param line_id: 线路lineId
        :param target_order: 所在公交站点ID
        :param city_id: city id from get_city method
        :param lat: 公交站点lat
        :param lng: 公交站点lng

        response data 简要说明:
        data/buses: 公交车信息
        data/buses/distanceToSc: 距离 distanceToWaitStn 站点的距离
        data/buses/distanceToWaitStn: -1表示下一站
        data/line: 线路信息
        data/otherlines: 对向的线路信息
        data/stations/distanceToSp: 上一站到本站距离
        data/stations/order: 站点序号
        data/stations/sId: 站点ID
        data/stations/sn: 站点名称
        data/stations/metros: 附近地铁站
        """
        params = {
            "cityId": city_id if city_id else self.city_id,
            "lineId": line_id,
            "targetOrder": target_order,
            "geo_lng": lng if lng else self.wgs_lng,
            "geo_lat": lat if lat else self.wgs_lat,
            "geo_type": "gcj",
            "isNewLineDetail": 1,
            "last_src": "app_xiaomi_store",
            "sign": self.sign,
            "s": self.s,
            "v": self.v,
        }
        response = self.curl_request(self.lineDetail, data=params)
        if response:
            data = self.replace_response_special_chars(response.text)
            json_data = json.loads(data)
            if json_data.get("jsonr", {}).get("status") == "00":
                return json_data["jsonr"]["data"]
        return None

    def get_buses_detail(self, target_order: str, line_id: str,
                         city_id: str = None, lat: str = None, lng: str = None) -> Optional[dict]:
        """
        获取公交车细节
        :param city_id: city id from get_city method
        :param lat: 纬度
        :param lng: 经度
        :param target_order: 所在公交站点ID
        :param line_id: 线路lineId
        :return:
        """
        params = {
            "targetOrder": target_order,
            "lineId": line_id,
            "geo_lng": lng if lng else self.wgs_lng,
            "geo_lat": lat if lat else self.wgs_lat,
            "cityId": city_id if city_id else self.city_id,
            "lat": lat if lat else self.wgs_lat,
            "geo_type": "gcj",
            "gpstype": "gcj",
            "geo_lt": 5,
            "screenDensity": 3.0,
            "flpolicy": 1,
            "stats_referer": "searchHistory",
            "sign": self.sign,
            "s": self.s,
            "v": self.v,
        }
        response = self.curl_request(self.busesDetail, data=params)
        if response:
            data = self.replace_response_special_chars(response.text)
            json_data = json.loads(data)
            if json_data.get("jsonr", {}).get("status") == "00":
                return json_data["jsonr"]["data"]
        return None

    def get_time_table(self, s_id: str, line_id: str, city_id: str = None,
                     lat: str = None, lng: str = None) -> Optional[dict]:
        """
        时间表
        :param s_id:    站点ID
        :param line_id: 线路ID
        :param city_id: city id from get_city method
        :param lat:   纬度
        :param lng:   经度
        """
        params = {
            "cityId": city_id if city_id else self.city_id,
            "stationId": s_id,
            "lineId": line_id,
            "geo_type": "gcj",
            "geo_lng": lng if lng else self.wgs_lng,
            "geo_lat": lat if lat else self.wgs_lat,
            "sign": self.sign,
            "s": self.s,
            "v": self.v,
        }
        response = self.curl_request(self.getBusTime, data=params)
        if response:
            data = self.replace_response_special_chars(response.text)
            json_data = json.loads(data)
            if json_data.get("jsonr", {}).get("status") == "00":
                return json_data["jsonr"]["data"]
        return None

    def get_geocodes(self, city: str, address: str, key: str = None) -> Optional[list]:
        key = key if key else config.get("amap", "key")
        params = {
            "key": key,
            "address": address,
            "city": city
        }
        response = self.curl_request(config.get("amap", "geo_url"), data=params)
        if response:
            json_data = response.json()
            if json_data.get("count") and json_data["geocodes"]:
                return json_data["geocodes"]
        return None

    def address_to_lat_lag(self, city: str, address: str, key: str = None) -> Optional[list]:
        key = key if key else config.get("amap", "key")
        geocodes = self.get_geocodes(city, address, key)
        if geocodes:
            location = geocodes[0].get("location")
            return location.split(",") if location else None
        return None
