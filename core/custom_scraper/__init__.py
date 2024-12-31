from core.utils.config import ConfigReader

config_reader = ConfigReader('config.ini')
custom_scraper_enabled = config_reader.get('DEFAULT', 'CUSTOM_SCRAPER_ENABLED', fallback=True)

if custom_scraper_enabled:
    from core.custom_scraper.mp import mp_scraper
    customer_crawler_map = {'mp.weixin.qq.com': mp_scraper}
else:
    customer_crawler_map = {}

