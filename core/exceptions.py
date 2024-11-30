from typing import Optional

class BusApiError(Exception):
    """基础API异常类"""
    def __init__(self, message: str, detail: Optional[str] = None):
        self.message = message
        self.detail = detail
        super().__init__(self.message)

class BusApiRequestError(BusApiError):
    """请求错误，如网络问题、超时等"""
    pass

class BusApiResponseError(BusApiError):
    """响应错误，如解析失败、业务错误等"""
    pass

class BusQueryError(Exception):
    """查询层异常"""
    pass
