#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from core.general_process import run_all_sites, wiseflow_logger
import sys
import traceback

def main():
    """
    主程序入口
    """
    try:
        wiseflow_logger.info('开始执行 WiseFlow 爬虫程序')
        asyncio.run(run_all_sites())
    except Exception as e:
        wiseflow_logger.error(f'程序执行出错: {e}')
        wiseflow_logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()
