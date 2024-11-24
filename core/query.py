import logging
import time
from typing import List, Dict, Optional
from dataclasses import dataclass

from config import config
from core.api import BusApi


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


class BusQuery:
    def __init__(self):
        self.api = BusApi()
        self.retry_attempts = 3
        self.retry_delay = 1  # seconds

    def _make_api_call_with_retry(self, func, *args, **kwargs) -> Optional[Dict]:
        """使用重试机制进行API调用"""
        for attempt in range(self.retry_attempts):
            try:
                data = func(*args, **kwargs)
                if data:
                    return data
            except Exception as e:
                logger.error(f"API call failed (attempt {attempt + 1}/{self.retry_attempts}): {str(e)}")
            if attempt < self.retry_attempts - 1:
                time.sleep(self.retry_delay)
        return None

    def get_lines_with_order(self) -> List[LineInfo]:
        """获取包含目标站点的所有线路信息"""
        lines = config.get("focus_line", [])
        target_station_name = config.get("target_station", {}).get("name")
        if not target_station_name:
            logger.error("Target station name not configured")
            return []

        target_station_in_line_order_list = []

        for line in lines:
            try:
                data = self._make_api_call_with_retry(
                    self.api.get_line_detail,
                    line_id=line["line_id"]
                )
                if not data:
                    logger.warning(f"Failed to get line detail for line: {line}")
                    continue

                stations = data.get("stations", [])
                for station in stations:
                    if station["sn"] == target_station_name:
                        line_info = LineInfo(
                            line_id=line["line_id"],
                            line_name=line["line_name"],
                            target_station_order=station["order"],
                            target_station_id=station["sId"],
                            target_station_name=station["sn"]
                        )
                        target_station_in_line_order_list.append(line_info)
                        break
            except Exception as e:
                logger.error(f"Error processing line {line}: {str(e)}")
                continue
        return target_station_in_line_order_list

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
            logger.error(f"Error processing bus info: {str(e)}")
            return None

    def query(self) -> List[Dict]:
        """查询所有线路的实时公交信息"""
        bus_realtime_info = []
        lines_with_order = self.get_lines_with_order()
        logger.info(f"query {len(lines_with_order)} lines with target station, line names: {', '.join([l.line_name for l in lines_with_order])}")

        for line in lines_with_order:
            try:
                data = self._make_api_call_with_retry(
                    self.api.get_line_detail,
                    line_id=line.line_id,
                    target_order=line.target_station_order
                )
                if not data:
                    logger.warning(f"Failed to get line detail for line {line.line_name}")
                    continue

                line_info = data.get("line", {})
                stations = data.get("stations", [])

                # 获取目标站点的下一站名称
                target_station_next_name = next(
                    (s["sn"] for s in stations if s["order"] == line.target_station_order + 1),
                    ""
                )

                # 处理每辆公交车的实时信息
                realtime_info_list = []
                for bus in data.get("buses", []):
                    bus_info = self.process_bus_info(
                        bus,
                        line.target_station_order,
                        stations
                    )
                    if bus_info:
                        realtime_info_list.append(bus_info)
                # realtime_info_list 排序, optimistic_time 越小越靠前
                realtime_info_list.sort(key=lambda x: x.get("optimistic_time", 0))

                # data/depDesc: "上一班6分钟前过站",
                dep_desc = data.get("depDesc", "")
                bus_realtime_info.append({
                    "line_id": line.line_id,
                    "line_name": line.line_name,
                    "line_info_short_desc": line_info.get("shortDesc", ""),
                    "line_desc": line_info.get("desc", ""),
                    "line_assist_desc": line_info.get("assistDesc", ""),
                    "target_station_name": line.target_station_name,
                    "target_station_next_station_name": target_station_next_name,
                    "realtime_bus_info": realtime_info_list
                })

            except Exception as e:
                logger.error(f"Error processing line {line.line_id}: {str(e)}")
                continue
        # bus_realtime_info 排序,
        # 根据 realtime_bus_info 中第一个元素的 optimistic_time 排序
        # realtime_bus_info 有可能为空，如果为空则放在最后
        bus_realtime_info.sort(
            key=lambda x: x["realtime_bus_info"][0].get("optimistic_time", float("inf"))
            if x["realtime_bus_info"] else float("inf")
        )
        logger.info(f"query result: {bus_realtime_info}")
        return bus_realtime_info

    def get_dep_time(self, line_id: str) -> Optional[list]:
        """获取线路的发车时间"""
        try:
            data = self._make_api_call_with_retry(
                self.api.get_time_table,
                line_id=line_id
            )
            if not data:
                logger.warning(f"Failed to get line detail for line {line_id}")
                return None
            return data.get("timetable", None)
        except Exception as e:
            logger.error(f"Error getting departure time for line {line_id}: {str(e)}")
            return None
