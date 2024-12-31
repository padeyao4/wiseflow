import configparser
import os

class ConfigReader:
    def __init__(self, config_file='config.ini'):
        # 初始化配置读取器，加载指定的配置文件
        self.config_file = config_file
        self.config = configparser.ConfigParser(default_section='DEFAULT')
        self.config.read(config_file)

    def get(self, section, option, fallback=None):
        # 获取指定节和选项的值，如果不存在则返回备用值
        value = self.config.get(section, option, fallback=fallback).strip("'\"")
        
        # 处理布尔值
        if value.lower() in ['true', 'false']:
            return value.lower() == 'true'
        
        # 处理数字
        try:
            return int(value) if value.isdigit() else value
        except ValueError:
            return value

    def get_all_sections(self):
        # 返回配置文件中所有节的名称
        return [section.strip() for section in self.config.sections()]

    def get_all_options(self, section):
        # 返回指定节中所有选项的名称
        return [option.strip() for option in self.config.options(section)]

    def set(self, section, option, value):
        # 设置配置项的值
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, option, str(value))
        self._save()

    def _save(self):
        # 保存配置文件
        with open(self.config_file, 'w') as configfile:
            self.config.write(configfile)

    def ensure_config_exists(self):
        # 确保配置文件存在，如果不存在则创建
        if not os.path.exists(self.config_file):
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                self.config.write(f)
