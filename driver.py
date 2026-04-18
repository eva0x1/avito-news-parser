import random
import traceback

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

try:
    from playwright_stealth import stealth_sync
except ImportError:
    stealth_sync = None

from config import USER_AGENTS
from logger_setup import logger


class DriverManager:
    """Обёртка над Playwright Chromium.
    Сохраняет интерфейс прежней Selenium-версии:
      driver_manager.driver → объект Page
      driver_manager.cookies() → список cookies как у Selenium (list[dict] c name/value).
    """

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    @property
    def driver(self):
        """Обратная совместимость: раньше был Selenium WebDriver, теперь Playwright Page."""
        return self.page

    def cookies(self):
        """Селениум-подобный список cookies, {name, value, ...}. Пусто если контекст не жив."""
        if self.context is None:
            return []
        try:
            return self.context.cookies()
        except Exception:
            return []

    def _build_proxy_config(self, proxy_settings):
        host = (proxy_settings.get('host') or '').strip()
        port = str(proxy_settings.get('port') or '').strip()
        if not host or not port:
            return None
        scheme = (proxy_settings.get('scheme') or 'http').lower()
        cfg = {"server": f"{scheme}://{host}:{port}"}
        user = (proxy_settings.get('user') or '').strip()
        pwd = (proxy_settings.get('pass') or '').strip()
        if user:
            cfg["username"] = user
        if pwd:
            cfg["password"] = pwd
        return cfg

    def create_driver(self, proxy_settings, log_callback=None):
        """Создаёт Playwright-инстанс. Возвращает Page или None при ошибке."""
        try:
            self.cleanup()

            proxy_config = self._build_proxy_config(proxy_settings)
            user_agent = random.choice(USER_AGENTS)

            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=True,
                proxy=proxy_config,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                ],
            )
            self.context = self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                locale="ru-RU",
            )
            self.page = self.context.new_page()
            self.page.set_default_timeout(15000)
            self.page.set_default_navigation_timeout(30000)

            if stealth_sync is not None:
                try:
                    stealth_sync(self.page)
                except Exception as e:
                    logger.warning(f"stealth_sync не применён: {e}")

            return self.page
        except Exception as e:
            error_trace = traceback.format_exc()
            if log_callback:
                log_callback(f"Ошибка создания драйвера: {str(e)}")
            logger.error(f"Ошибка создания драйвера: {error_trace}")
            self.cleanup()
            return None

    def ensure_driver(self, proxy_settings, log_callback=None):
        """Проверяет что драйвер жив, пересоздаёт если нет."""
        if self.page is None:
            return self.create_driver(proxy_settings, log_callback) is not None
        try:
            if self.page.is_closed():
                raise RuntimeError("Page is closed")
            _ = self.page.url
            return True
        except Exception:
            if log_callback:
                log_callback("Драйвер не отвечает, пересоздаём...")
            logger.warning("Драйвер не отвечает, пересоздаём...")
            self.cleanup()
            return self.create_driver(proxy_settings, log_callback) is not None

    def cleanup(self):
        for attr in ('page', 'context', 'browser'):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    if hasattr(obj, 'is_closed') and not obj.is_closed():
                        obj.close()
                    elif hasattr(obj, 'close'):
                        obj.close()
                except Exception:
                    pass
                setattr(self, attr, None)

        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
