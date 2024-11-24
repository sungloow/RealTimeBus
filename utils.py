from datetime import datetime


def get_now_time():
    """
    "%Y-%m-%d %H:%M:%S" format time
    :return:
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")