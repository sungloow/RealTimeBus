import json
import os
import unittest

from config import config
from core.api import BusApi
from core.query import BusQuery


class TestApi(unittest.TestCase):
    def setUp(self):
        self.api = BusApi()
        self.query = BusQuery()

    def test_get_city(self):
        city_data = self.api.get_city()
        assert city_data is not None
        print(json.dumps(city_data, ensure_ascii=False, indent=4))

    def test_get_home_page_info(self):
        home_page_info = self.api.get_arr()
        assert home_page_info is not None
        print(json.dumps(home_page_info, ensure_ascii=False, indent=4))

    def test_get_line_detail(self):
        bus_info = self.api.get_line_detail(line_id='023-625-0')
        assert bus_info is not None
        print(json.dumps(bus_info, ensure_ascii=False, indent=4))

    def test_get_buses_detail(self):
        line_detail = self.api.get_buses_detail(target_order='1340', line_id='023-625-0')
        assert line_detail is not None
        print(json.dumps(line_detail, ensure_ascii=False, indent=4))

    def test_amap(self):
        amap = self.api.get_geocodes("重庆", "康庄美地E区公交站")
        assert amap is not None
        print(json.dumps(amap, ensure_ascii=False, indent=4))

    def test_config(self):
        lines = config.get("focus_line")
        assert lines is not None
        print(json.dumps(lines, ensure_ascii=False, indent=4))

    def test_query(self):
        info = self.query.query()
        print(json.dumps(info, ensure_ascii=False, indent=4))

    def test_calculate_distance(self):
        file_path = os.path.join(os.path.dirname(__file__), "data/stations.json")
        with open(file_path, "r", encoding="utf-8") as file:
            stations = json.load(file)
        distance = self.query.calculate_distance(stations, 12, 14)
        assert distance == 1440+1613
