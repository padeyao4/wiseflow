# -*- coding: utf-8 -*-
from core.utils.pb_api import PbTalker  # 导入PbTalker类，用于与PocketBase进行交互
from core.utils.general_utils import get_logger, extract_and_convert_dates  # 导入日志记录和日期提取工具
from core.agents.get_info import GeneralInfoExtractor  # 导入通用信息提取器
from bs4 import BeautifulSoup  # 导入BeautifulSoup库，用于解析HTML
import os  # 导入os模块，用于操作系统相关功能
import json  # 导入json模块，用于处理JSON数据
from core.custom_scraper import customer_crawler_map  # 导入自定义爬虫映射
from urllib.parse import urlparse, urljoin  # 导入URL解析和连接工具
from crawlee.playwright_crawler import PlaywrightCrawler, PlaywrightCrawlingContext, PlaywrightPreNavigationContext  # 导入爬虫相关类
from datetime import datetime, timedelta  # 导入日期和时间处理工具
from core.utils.config import ConfigReader


# 读取配置文件
config_reader = ConfigReader('config.ini')

project_dir = config_reader.get('DEFAULT', 'PROJECT_DIR', fallback='')  # 从配置文件中获取项目目录
if project_dir:
    os.makedirs(project_dir, exist_ok=True)  # 如果项目目录不存在，则创建

# 设置爬虫存储目录
os.environ['CRAWLEE_STORAGE_DIR'] = os.path.join(project_dir, 'crawlee_storage')
screenshot_dir = os.path.join(project_dir, 'crawlee_storage', 'screenshots')  # 设置截图存储目录
wiseflow_logger = get_logger('general_process', project_dir)  # 获取日志记录器
pb = PbTalker(wiseflow_logger)  # 初始化PbTalker
gie = GeneralInfoExtractor(pb, wiseflow_logger)  # 初始化信息提取器
existing_urls = {url['url'] for url in pb.read(collection_name='infos', fields=['url'])}  # 读取已存在的URL


async def save_to_pb(url: str, infos: list):
    # 保存到pb的过程
    for info in infos:
        info['url'] = url  # 将URL添加到信息中
        _ = pb.add(collection_name='infos', body=info)  # 添加信息到PocketBase
        if not _:
            wiseflow_logger.error('添加信息失败，写入缓存文件')  # 记录错误日志
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")  # 获取当前时间戳
            with open(os.path.join(project_dir, f'{timestamp}_cache_infos.json'), 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=4)  # 将信息写入缓存文件


# 使用配置控制爬虫参数
max_requests = config_reader.get('DEFAULT', 'MAX_REQUESTS_PER_CRAWL', fallback=None)
request_timeout = config_reader.get('DEFAULT', 'REQUEST_TIMEOUT', fallback=5)

crawler = PlaywrightCrawler(
    max_requests_per_crawl=int(max_requests),  # 转换为整数或 None
    max_request_retries=1,
    request_handler_timeout=timedelta(minutes=int(request_timeout)),
)

@crawler.pre_navigation_hook
async def log_navigation_url(context: PlaywrightPreNavigationContext) -> None:
    context.log.info(f'Navigating to {context.request.url} ...')  # 记录导航的URL

@crawler.router.default_handler
async def request_handler(context: PlaywrightCrawlingContext) -> None:
    # 处理请求的函数
    # context.log.info(f'Processing {context.request.url} ...')
    # 处理对话框（警报、确认、提示）
    async def handle_dialog(dialog):
        context.log.info(f'Closing dialog: {dialog.message}')  # 记录关闭的对话框信息
        await dialog.accept()  # 接受对话框

    context.page.on('dialog', handle_dialog)  # 监听对话框事件
    await context.page.wait_for_load_state('networkidle')  # 等待网络空闲状态
    html = await context.page.inner_html('body')  # 获取页面HTML
    context.log.info('successfully finish fetching')  # 记录成功获取信息

    # 解析URL
    parsed_url = urlparse(context.request.url)  # 解析请求的URL
    domain = parsed_url.netloc  # 获取域名
    if domain in custom_scraper_map:
        context.log.info(f'路由到客户爬虫 {domain}')  # 记录路由到客户爬虫
        try:
            # 使用客户爬虫处理
            article, more_urls, infos = await custom_scraper_map[domain](html, context.request.url)
            if not article and not infos and not more_urls:
                wiseflow_logger.warning(f'{parsed_url} 被客户爬虫处理，但没有获取到任何内容')  # 记录警告日志
        except Exception as e:
            context.log.error(f'发生错误: {e}')  # 记录错误日志
            wiseflow_logger.warning(f'客户爬虫处理 {parsed_url} 失败，无法找到信息')  # 记录警告日志
            article, infos, more_urls = {}, [], set()  # 初始化变量

        link_dict = more_urls if isinstance(more_urls, dict) else {}  # 获取链接字典
        related_urls = more_urls if isinstance(more_urls, set) else set()  # 获取相关URL
        if not infos and not related_urls:
            try:
                text = article.get('content', '')  # 获取文章内容
            except Exception as e:
                wiseflow_logger.warning(f'customer scraper output article is not valid dict: {e}')  # 记录警告日志
                text = ''  # 初始化文本

            if not text:
                wiseflow_logger.warning(f'no content found in {parsed_url} by customer scraper, cannot use llm GIE, aborting')  # 记录警告日志
                infos, related_urls = [], set()  # 初始化信息和相关URL
            else:
                author = article.get('author', '')  # 获取作者
                publish_date = article.get('publish_date', '')  # 获取发布日期
                # 通过LLM获取信息
                try:
                    infos, related_urls, author, publish_date = await gie(text, link_dict, context.request.url, author, publish_date)
                except Exception as e:
                    wiseflow_logger.error(f'gie error occurred in processing: {e}')  # 记录错误日志
                    infos, related_urls = [], set()  # 初始化信息和相关URL
    else:
        # 从页面提取数据
        # 未来工作：尝试使用视觉LLM完成所有工作...
        text = await context.page.inner_text('body')  # 获取页面文本
        soup = BeautifulSoup(html, 'html.parser')  # 解析HTML
        links = soup.find_all('a', href=True)  # 查找所有链接
        base_url = f"{parsed_url.scheme}://{domain}"  # 构建基本URL
        link_dict = {}  # 初始化链接字典
        for a in links:
            new_url = a.get('href')  # 获取链接
            if new_url.startswith('javascript:') or new_url.startswith('#') or new_url.startswith('mailto:'):
                continue  # 跳过无效链接
            if new_url in [context.request.url, base_url]:
                continue  # 跳过当前请求的URL和基本URL
            if new_url in existing_urls:
                continue  # 跳过已存在的URL
            t = a.text.strip()  # 获取链接文本
            if new_url and t:
                link_dict[t] = urljoin(base_url, new_url)  # 将链接添加到字典
                existing_urls.add(new_url)  # 添加到已存在的URL集合

        publish_date = soup.find('div', class_='date').get_text(strip=True) if soup.find('div', class_='date') else None  # 获取发布日期
        if publish_date:
            publish_date = extract_and_convert_dates(publish_date)  # 转换发布日期格式
        author = soup.find('div', class_='author').get_text(strip=True) if soup.find('div', class_='author') else None  # 获取作者
        if not author:
            author = soup.find('div', class_='source').get_text(strip=True) if soup.find('div', class_='source') else None  # 获取来源
        # 通过LLM获取信息
        infos, related_urls, author, publish_date = await gie(text, link_dict, base_url, author, publish_date)

    if infos:
        await save_to_pb(context.request.url, infos)  # 保存信息到PocketBase

    if related_urls:
        await context.add_requests(list(related_urls))  # 添加相关请求

    # todo: 使用LLM确定下一步操作
    """
    screenshot_file_name = f"{hashlib.sha256(context.request.url.encode()).hexdigest()}.png"  # 生成截图文件名
    await context.page.screenshot(path=os.path.join(screenshot_dir, screenshot_file_name), full_page=True)  # 截图
    wiseflow_logger.debug(f'screenshot saved to {screenshot_file_name}')  # 记录截图保存信息
    """

async def run_all_sites():
    sites = pb.read('sites', filter='activated=True')  # 读取激活的站点
    wiseflow_logger.info('执行所有站点一次')  # 记录执行信息
    await crawler.run([site['url'].rstrip('/') for site in sites])  # 运行所有站点
