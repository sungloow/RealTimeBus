import json

from fastapi import FastAPI, HTTPException, Depends, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional, Union
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

# 获取日志记录器
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

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: str = Field(description="响应时间")

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

# 依赖项：获取BusQuerySystem实例
async def get_bus_query_system():
    return BusQuery()

# 自定义异常处理
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            timestamp=get_now_time()
        ).dict()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc),
            timestamp=get_now_time()
        ).dict()
    )

# API路由
@app.get("/", response_model=dict)
async def root():
    """API根路径，返回基本信息"""
    return {
        "service": "实时公交查询服务",
        "version": "1.0.0",
        "status": "running",
        "timestamp": get_now_time()
    }

@app.get("/api/v1/bus/realtime", response_model=RealtimeResponse)
async def get_realtime_bus_info(
        bus_query: BusQuery = Depends(get_bus_query_system)
):
    """
    获取实时公交信息

    返回:
        status: 状态码
        message: 状态描述
        total: 返回的线路总数
        timestamp: 响应时间
        data: 所有配置线路的实时公交信息
        frontlimit: 前端限制显示的线路数量
    """
    front_limit = 2
    try:
        # 创建异步任务
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, bus_query.query)
        # 构造响应
        response = RealtimeResponse(
            status=200,
            message="success",
            total=len(results),
            timestamp=get_now_time(),
            data=results,
            frontlimit=front_limit
        )
        return response
    except Exception as e:
        logger.error(f"Error fetching bus information: {str(e)}", exc_info=True)
        # 返回错误响应
        return RealtimeResponse(
            status=500,
            message=f"Failed to fetch bus information.",
            total=0,
            timestamp=get_now_time(),
            data=[],
            frontlimit=front_limit
        )

@app.get("/api/v1/bus/line/{line_name}", response_model=RealtimeResponse)
async def get_line_info(
        line_name: str,
        bus_query: BusQuery = Depends(get_bus_query_system)
):
    """
    获取指定线路的实时信息
    """
    try:
        results = await asyncio.get_event_loop().run_in_executor(None, bus_query.query)
        line_info = next((line for line in results if line["line_name"] == line_name), None)

        if not line_info:
            raise RealtimeResponse(
                status=404,
                message=f"Line {line_name} not found",
                total=0,
                timestamp=get_now_time(),
                data=[]
            )
        return RealtimeResponse(
            status=200,
            message="success",
            total=1,
            timestamp=get_now_time(),
            data=[line_info]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching line information: {str(e)}", exc_info=True)
        raise RealtimeResponse(
            status=500,
            message=f"Failed to fetch line information.",
            total=0,
            timestamp=get_now_time(),
            data=[]
        )

# 健康检查接口
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "timestamp": get_now_time()}

@app.get("/test")
async def test(file_name: Union[str, None] = Query(default="mock.json", description="The name of the file to read")):
    """test"""
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

# 用于开发环境的启动代码
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )