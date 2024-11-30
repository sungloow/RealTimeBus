import logging
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
import asyncio
from cachetools import TTLCache

from config import config
from core.api import BusApi
from core.exceptions import BusApiError, BusQueryError

logger = logging.getLogger(__name__)


@dataclass
class LineInfo:
    line_id: str
    line_name: str
    target_station_order: int
    target_station_id: str
    target_station_name: str


def convert_time_to_str(minutes: int) -> str:
    """将秒数转换为时间字符串"""
    if minutes < 60:
        return f"{minutes}秒"
    if minutes % 60 == 0:
        return f"{minutes // 60}分钟"
    return f"{minutes // 60}分钟{minutes % 60}秒"


line_cache = TTLCache(maxsize=len(config.get("focus_line", [])) * 2, ttl=config.get("system", "line_cache_ttl", 60*60*24))
line_real_cache = TTLCache(maxsize=len(config.get("focus_line", [])) * 2, ttl=config.get("system", "line_real_cache_ttl", 10))


class BusQuery:
    def __init__(self):
        self.api = BusApi()

    def _get_target_station_info(self) -> tuple[list, str]:
        """获取目标站点配置信息"""
        config.refresh()
        lines = config.get("focus_line", [])
        target_station_name = config.get("target_station", {}).get("name")
        if not target_station_name:
            raise BusQueryError("Target station name not configured")
        return lines, target_station_name

    async def _fetch_line_details(self, lines: List[Dict]) -> List[Dict]:
        """获取所有线路详情"""
        tasks = [self.api.async_get_line_detail(line_id=line["line_id"]) for line in lines]
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        except Exception as e:
            raise BusQueryError(f"Failed to gather line details: {str(e)}")

    def _process_line_detail(self, line: Dict, target_station_name: str) -> Optional[LineInfo]:
        """处理单条线路详情，主要是找到目标站点在该线路中的站点序号"""
        try:
            line_info = line.get("line", {})
            line_stations = line.get("stations", [])
            for station in line_stations:
                if station["sn"] == target_station_name:
                    return LineInfo(
                        line_id=line_info["lineId"],
                        line_name=line_info["name"],
                        target_station_order=station["order"],
                        target_station_id=station["sId"],
                        target_station_name=station["sn"]
                    )
            return None
        except Exception as e:
            logger.error(f"Error processing line data: {str(e)}, data: {line}")
            return None

    async def get_lines_with_order(self) -> List[LineInfo]:
        """获取包含目标站点的所有线路信息"""
        try:
            # 获取配置信息
            lines, target_station_name = self._get_target_station_info()
            # 检查缓存，key 为 lines_with_order_每个线路的line_id
            cache_key = f"lines_with_order_{'@'.join([line['line_id'] for line in lines])}"
            if cached_data := line_cache.get(cache_key):
                return cached_data
            logger.info(f"Lines with order cache key: {cache_key} not found, fetching data")
            # 获取线路详情
            line_details = await self._fetch_line_details(lines)
            # 处理每条线路
            target_station_in_line_order_list = []
            for line in line_details:
                if isinstance(line, Exception):
                    logger.error(f"Error fetching line detail: {str(line)}")
                    continue
                if not line:
                    continue
                if line_info := self._process_line_detail(line, target_station_name):
                    target_station_in_line_order_list.append(line_info)
            if not target_station_in_line_order_list:
                logger.warning(f"No lines found with target station: {target_station_name}")
            # 更新缓存
            line_cache[cache_key] = target_station_in_line_order_list
            return target_station_in_line_order_list
        except BusApiError as e:
            logger.error(f"API error in get_lines_with_order: {str(e)}")
            raise BusQueryError(f"Failed to get lines: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in get_lines_with_order: {str(e)}")
            raise BusQueryError(f"Unexpected error: {str(e)}")

    async def _fetch_line_data(self, line: LineInfo) -> Optional[Dict]:
        """获取线路数据，优先从缓存获取"""
        cache_key = f"line_{line.line_id}"
        if cached_data := line_real_cache.get(cache_key):
            return cached_data
        # logger.info(f"Line cache key: {cache_key} not found, fetching data")
        try:
            data = await self.api.async_get_line_detail(
                line_id=line.line_id,
                target_order=line.target_station_order
            )
            if not data:
                logger.warning(f"No data returned for line {line.line_name}")
                return None

            result = {
                "line_info": data.get("line", {}),
                "stations": data.get("stations", []),
                "buses": data.get("buses", [])
            }

            line_real_cache[cache_key] = result
            return result

        except BusApiError as e:
            logger.error(f"API error fetching line detail: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error fetching line detail: {str(e)}")
            return None

    def _get_next_station_name(self, stations: List[Dict], target_station_order: int) -> str:
        """获取目标站点的下一站名称"""
        return next(
            (s["sn"] for s in stations if s["order"] == target_station_order + 1),
            ""
        )

    async def async_query_line(self, line: LineInfo) -> Optional[Dict]:
        """异步查询单条线路信息"""
        try:
            # 获取线路数据
            line_data = await self._fetch_line_data(line)
            if not line_data:
                return None

            line_info = line_data["line_info"]
            stations = line_data["stations"]
            buses = line_data["buses"]

            # 获取下一站名称
            target_station_next_name = self._get_next_station_name(stations, line.target_station_order)

            # 处理实时公交信息
            realtime_info_list = []
            for bus in buses:
                if bus_info := self.process_bus_info(bus, line.target_station_order, stations):
                    realtime_info_list.append(bus_info)

            realtime_info_list.sort(key=lambda x: x.get("optimistic_time", 0))

            # 构建返回数据
            return {
                "line_id": line.line_id,
                "line_name": line.line_name,
                "line_info_short_desc": line_info.get("shortDesc", ""),
                "line_desc": line_info.get("desc", ""),
                "line_assist_desc": line_info.get("assistDesc", ""),
                "target_station_name": line.target_station_name,
                "target_station_next_station_name": target_station_next_name,
                "realtime_bus_info": realtime_info_list
            }

        except Exception as e:
            logger.error(f"Unexpected error in async_query_line: {str(e)}")
            return None

    async def async_query(self) -> List[Dict]:
        """异步并行查询所有线路的实时公交信息"""
        try:
            lines_with_order = await self.get_lines_with_order()
            logger.info(f"query {len(lines_with_order)} lines with target station, line names: {', '.join([l.line_name for l in lines_with_order])}")

            tasks = [self.async_query_line(line) for line in lines_with_order]
            results = await asyncio.gather(*tasks)

            bus_realtime_info = [r for r in results if r is not None]
            bus_realtime_info.sort(
                key=lambda x: x["realtime_bus_info"][0].get("optimistic_time", float("inf"))
                if x["realtime_bus_info"] else float("inf")
            )
            return bus_realtime_info
        except Exception as e:
            logger.error(f"Unexpected error in async_query: {str(e)}")
            return []

    @staticmethod
    def calculate_distance(stations: List[Dict], start_order: int, end_order: int) -> int:
        """计算站点之间的距离"""
        try:
            if start_order <= 0 or end_order <= 0:
                raise ValueError(f"Invalid order values: start={start_order}, end={end_order}")

            if start_order == end_order:
                return 0

            if start_order > end_order:
                start_order, end_order = end_order, start_order

            distance = 0
            for station in stations:
                if start_order < station["order"] <= end_order:
                    distance += station.get("distanceToSp", 0)
            return distance

        except Exception as e:
            logger.error(f"Error calculating distance: {str(e)}")
            return 0

    def process_bus_info(self, bus: Dict, target_order: int, stations: List[Dict]) -> Optional[Dict]:
        """处理单个公交车的实时信息"""
        try:
            bus_next_order = bus["order"]
            if bus_next_order > target_order:
                return None

            bus_id = bus["busId"]
            distance_to_sc = bus.get("distanceToSc", 0)
            distance_to_wait_stn = bus.get("distanceToWaitStn", 0)
            begin_order = bus_next_order + abs(distance_to_wait_stn) - 1

            distance_to_target = self.calculate_distance(
                stations, begin_order, target_order
            ) + distance_to_sc

            # buses/delayDesc 到站时间不准， delay : 1
            delay = bus["delay"]
            delay_desc = bus["delayDesc"]
            # 处理到站时间信息
            opt_arrival_time = 0
            optimistic_time = 0
            for travel in bus.get("travels", []):
                if travel["order"] == target_order:
                    opt_arrival_time = travel.get("optArrivalTime", 0)
                    optimistic_time = travel.get("optimisticTime", 0)
                    break
            #  大于1000米用公里表示，小于1000米用米表示
            distance_to_target_format = (
                f"{distance_to_target / 1000:.1f}公里"
                if distance_to_target >= 1000
                else f"{distance_to_target}米"
            )
            opt_arrival_time_display = "已到站"
            optimistic_time_display = "已到站"
            bus_desc = "已到站"
            if delay:
                opt_arrival_time_display = delay_desc
                optimistic_time_display = delay_desc
                bus_desc = delay_desc
            elif opt_arrival_time:
                opt_arrival_time_display = time.strftime("%H:%M:%S", time.localtime(opt_arrival_time / 1000))
                optimistic_time_display = convert_time_to_str(optimistic_time)
                bus_desc = "即将到站" if bus_next_order == target_order else "正在途中"

            return {
                "bus_id": bus_id,
                "distance_to_target": distance_to_target,
                "distance_to_target_display": distance_to_target_format,
                "opt_arrival_time": opt_arrival_time,
                "optimistic_time": optimistic_time,
                "opt_arrival_time_display": opt_arrival_time_display,
                "optimistic_time_display": optimistic_time_display,
                "number_of_stations_away": f"{target_order - bus_next_order}站",
                "desc": bus_desc,
            }
        except Exception as e:
            logger.error(f"Error processing bus info: {str(e)}, bus data: {bus}")
            return None

    async def get_dep_time(self, line_id: str) -> Optional[list]:
        """获取线路的发车时间"""
        try:
            data = await self.api.get_time_table(line_id=line_id)
            if not data:
                logger.warning(f"Failed to get line detail for line {line_id}")
                return None
            return data.get("timetable", None)
        except Exception as e:
            logger.error(f"Error getting departure time for line {line_id}: {str(e)}")
            return None
