"""
API 密钥容灾路由模块
功能：从配置文件提取 api_keys 并提供平滑轮换及失败重试机制。
"""
import os
import yaml
import time
from pathlib import Path
from rich.console import Console

console = Console()

class KeysManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KeysManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """从 sources.yaml 加载 API Key 配置"""
        self.keys_pool = {}
        self.current_indexes = {}
        
        # 尝试读取 config
        config_path = Path("sources.yaml")
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    self.keys_pool = config.get("api_keys", {})
            except Exception as e:
                console.print(f"[red]❌ 解析 sources.yaml 读取 API Keys 时出错: {e}[/red]")
        
        # 将环境变量作为额外的 fallback 推入 gemini_pool，前提是 pool 没有这个 key
        env_gemini = os.environ.get("GEMINI_API_KEY", "").strip()
        if env_gemini:
            gemini_keys = self.keys_pool.setdefault("gemini", [])
            if env_gemini not in gemini_keys:
                gemini_keys.append(env_gemini)

        # 初始化轮询索引
        for provider in self.keys_pool:
            self.current_indexes[provider] = 0

    def get_key(self, provider: str = "gemini") -> str:
        """获取指定模型的当前可用密钥"""
        keys = self.keys_pool.get(provider, [])
        if not keys:
            return ""
        idx = self.current_indexes.get(provider, 0)
        return keys[idx % len(keys)]

    def mark_key_failed(self, provider: str = "gemini"):
        """标记当前 Key 失败，轮换至下一个 Key"""
        keys = self.keys_pool.get(provider, [])
        if not keys:
            return
            
        old_idx = self.current_indexes.get(provider, 0)
        self.current_indexes[provider] = (old_idx + 1) % len(keys)
        new_idx = self.current_indexes[provider]
        
        # 脱敏打印日志
        old_k = keys[old_idx % len(keys)][:8] + "..."
        new_k = keys[new_idx % len(keys)][:8] + "..."
        console.print(f"  [yellow]🔄 {provider} API Key 切换: {old_k} -> {new_k}[/yellow]")

    def execute_with_fallback(self, provider: str, max_retries_per_key: int, task_func, *args, **kwargs):
        """
        容灾执行器包裹：
        对给定的 task_func 进行调用执行，每次传入一个 api_key 参数。
        当遇到特定报错（如 RateLimit, QuotaExceeded 等）时，尝试利用当前账户等待或者立刻切换至下一个账户进行流转。
        
        task_func 必须接受 api_key 作为 keyword argument，比如 task_func(..., api_key=key)
        返回: 执行成功的结果
        异常: 所有 key 全竭尽且重试失败后抛出异常
        """
        keys_count = max(1, len(self.keys_pool.get(provider, [])))
        # 最多遍历一圈密钥，防止无限死循环
        max_total_attempts = keys_count * max_retries_per_key
        
        for attempt in range(max_total_attempts):
            current_key = self.get_key(provider)
            if not current_key:
                raise ValueError(f"没有为 {provider} 找到可用的 API Key！")
                
            try:
                # 注入 api_key 给被包裹的闭包
                return task_func(api_key=current_key, *args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                
                # 确定是否是典型的风控、限流、超额或者无效Key异常以决定要不要马上切换 Key
                needs_switch_key = any(x in error_msg for x in ["quota", "403", "429", "exhausted", "permission denied", "invalid", "400"])
                
                if needs_switch_key:
                    console.print(f"  [red]✗ 执行失败 (触发 Key 熔断): {e}[/red]")
                    self.mark_key_failed(provider)
                else:
                    # 也许只是暂时的网络抖动，不用切号，尝试等待重试
                    wait_time = 5 * ((attempt % max_retries_per_key) + 1)
                    console.print(f"  [yellow]✗ 执行失败，正在本地重试 ({wait_time}s) ... 错误: {e}[/yellow]")
                    time.sleep(wait_time)
                    
        raise RuntimeError(f"所有 {provider} 关联的 {max_total_attempts} 次充试操作均失败，业务中断。")

# 提供单例实例以便全局使用
keys_manager = KeysManager()
