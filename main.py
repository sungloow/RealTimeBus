import json
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from typing import List, Union
from pydantic import BaseModel, Field
import uvicorn
import asyncio
import logging
from core.query import BusQuery
from utils import get_now_time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s[%(lineno)d] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 响应模型
class BusInfo(BaseModel):
    bus_id: str
    distance_to_target: int
    distance_to_target_display: str
    opt_arrival_time: int
    optimistic_time: int
    opt_arrival_time_display: str
    optimistic_time_display: str
    number_of_stations_away: str
    desc: str

class LineRealTimeInfo(BaseModel):
    line_id: str
    line_name: str
    line_info_short_desc: str
    line_desc: str
    line_assist_desc: str
    target_station_name: str
    target_station_next_station_name: str
    realtime_bus_info: List[BusInfo]

class RealtimeResponse(BaseModel):
    status: int = Field(description="状态码，200表示成功")
    message: str = Field(description="状态描述")
    total: int = Field(description="返回的线路总数")
    timestamp: str = Field(description="响应时间")
    data: List[LineRealTimeInfo] = Field(description="实时公交数据")
    frontlimit: int = Field(default=1, description="前端限制显示的线路数量")

class TimeTable(BaseModel):
    eTime: str
    fTime: str
    times: List[str]

class TimeTableResponse(BaseModel):
    status: int = Field(description="状态码，200表示成功")
    message: str = Field(description="状态描述")
    timestamp: str = Field(description="响应时间")
    data: List[TimeTable] = Field(description="发车时间表")


# 自定义异常类
class CustomException(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message

# 创建 FastAPI 应用
app = FastAPI(
    title="实时公交查询API",
    description="提供实时公交到站信息查询服务",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自定义异常处理
@app.exception_handler(CustomException)
async def custom_exception_handler(request: Request, exc: CustomException):
    logger.error(f"CustomException: {exc.message}")
    return JSONResponse(
        status_code=exc.status,
        content={"status": exc.status, "message": exc.message}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTPException: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": exc.status_code, "message": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": 500, "message": "Internal Server Error"}
    )

# 依赖项：获取BusQuerySystem实例
async def get_bus_query_system():
    return BusQuery()

# API路由
@app.get("/api/v1", response_model=dict)
async def root():
    return {
        "service": "实时公交查询服务",
        "version": "1.0.0",
        "status": "running",
        "timestamp": get_now_time()
    }

@app.get("/api/v1/bus/realtime", response_model=RealtimeResponse)
async def get_realtime_bus_info(bus_query: BusQuery = Depends(get_bus_query_system)):
    front_limit = 2
    try:
        results = await bus_query.async_query()
        if not results:
            raise CustomException(
                status=404,
                message="Realtime bus data could not be retrieved."
            )
        return RealtimeResponse(
            status=200,
            message="success",
            total=len(results),
            timestamp=get_now_time(),
            data=results,
            frontlimit=front_limit
        )
    except CustomException:
        raise
    except Exception as e:
        raise CustomException(
            status=500,
            message="Failed to fetch bus information"
        )

@app.get("/api/v1/bus/time/{line_id}", response_model=TimeTableResponse)
async def get_line_time(line_id: str, bus_query: BusQuery = Depends(get_bus_query_system)):
    try:
        results = await bus_query.get_dep_time(line_id)
        if not results:
            raise CustomException(
                status=404,
                message=f"Line {line_id} does not exist."
            )
        return TimeTableResponse(
            status=200,
            message="success",
            timestamp=get_now_time(),
            data=results
        )
    except CustomException:
        raise
    except Exception as e:
        raise CustomException(
            status=500,
            message="Failed to fetch line time"
        )

@app.get("/api/v1/bus/line/{line_name}", response_model=RealtimeResponse)
async def get_line_info(line_name: str, bus_query: BusQuery = Depends(get_bus_query_system)):
    try:
        results = await bus_query.async_query()
        line_info = next((line for line in results if line["line_name"] == line_name), None)
        if not line_info:
            raise CustomException(
                status=404,
                message=f"Line {line_name} does not exist."
            )
        return RealtimeResponse(
            status=200,
            message="success",
            total=1,
            timestamp=get_now_time(),
            data=[line_info]
        )
    except CustomException:
        raise
    except Exception as e:
        raise CustomException(
            status=500,
            message="Failed to fetch line information"
        )

@app.get("/test")
async def test(file_name: Union[str, None] = Query(default="mock.json", description="The name of the file to read")):
    logger.info(f"file_name: {file_name}")
    try:
        with open(f"test/data/{file_name}", "r", encoding="utf-8") as file:
            data = json.load(file)
        return data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": get_now_time()}

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("bus.html", {"request": request})

# 启动代码
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
