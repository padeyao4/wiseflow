import os
from pocketbase import PocketBase  # Client also works the same
from pocketbase.client import FileUpload
from typing import BinaryIO, Optional, List, Dict
from core.utils.config import ConfigReader
from loguru import logger


class PbTalker:
    def __init__(self, logger) -> None:
        config_reader = ConfigReader('config.ini')
        
        # 读取 PocketBase 配置
        self.pb_api_base = config_reader.get('DEFAULT', 'PB_API_BASE', fallback='http://127.0.0.1:8090')
        self.pb_email = config_reader.get('DEFAULT', 'PB_EMAIL', fallback='')
        self.pb_password = config_reader.get('DEFAULT', 'PB_PASSWORD', fallback='')
        
        # 初始化 PocketBase 客户端
        self._init_client()

    def _init_client(self):
        self.logger = logger
        self.logger.debug(f"initializing pocketbase client: {self.pb_api_base}")
        self.client = PocketBase(self.pb_api_base)
        
        # 检查认证信息
        if not self.pb_email or not self.pb_password:
            self.logger.warning("未提供 PocketBase 认证信息，将以匿名模式运行。请确保集合权限已正确设置。")
            return

        try:
            # 尝试管理员认证
            admin_data = self.client.admins.auth_with_password(self.pb_email, self.pb_password)
            if admin_data:
                self.logger.info(f"成功以管理员身份 {self.pb_email} 登录")
                return
        except Exception as admin_auth_error:
            self.logger.debug(f"管理员认证失败: {admin_auth_error}")

        try:
            # 尝试用户认证
            user_data = self.client.collection("users").auth_with_password(self.pb_email, self.pb_password)
            if user_data:
                self.logger.info(f"成功以用户身份 {self.pb_email} 登录")
                return
        except Exception as user_auth_error:
            self.logger.debug(f"用户认证失败: {user_auth_error}")
            self.logger.warning("PocketBase 认证失败，将以匿名模式运行。请检查凭据和权限。")

    def read(self, collection_name: str, fields: Optional[List[str]] = None, filter: str = '', skiptotal: bool = True) -> list:
        results = []
        i = 1
        while True:
            try:
                res = self.client.collection(collection_name).get_list(i, 500,
                                                                       {"filter": filter,
                                                                        "fields": ','.join(fields) if fields else '',
                                                                        "skiptotal": skiptotal})

            except Exception as e:
                self.logger.error(f"pocketbase get list failed: {e}")
                continue
            if not res.items:
                break
            for _res in res.items:
                attributes = vars(_res)
                results.append(attributes)
            i += 1
        return results

    def add(self, collection_name: str, body: Dict) -> str:
        try:
            res = self.client.collection(collection_name).create(body)
        except Exception as e:
            self.logger.error(f"pocketbase create failed: {e}")
            return ''
        return res.id

    def update(self, collection_name: str, id: str, body: Dict) -> str:
        try:
            res = self.client.collection(collection_name).update(id, body)
        except Exception as e:
            self.logger.error(f"pocketbase update failed: {e}")
            return ''
        return res.id

    def delete(self, collection_name: str, id: str) -> bool:
        try:
            res = self.client.collection(collection_name).delete(id)
        except Exception as e:
            self.logger.error(f"pocketbase update failed: {e}")
            return False
        if res:
            return True
        return False

    def upload(self, collection_name: str, id: str, key: str, file_name: str, file: BinaryIO) -> str:
        try:
            res = self.client.collection(collection_name).update(id, {key: FileUpload((file_name, file))})
        except Exception as e:
            self.logger.error(f"pocketbase update failed: {e}")
            return ''
        return res.id

    def view(self, collection_name: str, item_id: str, fields: Optional[List[str]] = None) -> Dict:
        try:
            res = self.client.collection(collection_name).get_one(item_id, {"fields": ','.join(fields) if fields else ''})
            return vars(res)
        except Exception as e:
            self.logger.error(f"pocketbase view item failed: {e}")
            return {}
