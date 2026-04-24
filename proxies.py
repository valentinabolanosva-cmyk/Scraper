"""
=====================================
  MÓDULO DE ROTACIÓN DE PROXIES
  Respeta config.USE_PROXY y config.MANUAL_PROXIES.
  Si USE_PROXY=False, load()/get_next() son no-op
  y devuelven None (scraper funciona sin proxy).
=====================================
"""

import itertools
import logging
from typing import Optional

import config

logger = logging.getLogger("FacebookScraper")


class ProxyRotator:
    def __init__(self):
        self.enabled: bool = bool(getattr(config, "USE_PROXY", False))
        self.rotation_every: int = int(getattr(config, "PROXY_ROTATION_EVERY", 10))
        self._proxies: list = []
        self._cycle = None
        self._uses_since_rotation: int = 0
        self._current: Optional[str] = None

    def load(self) -> None:
        """Carga la lista de proxies desde config.MANUAL_PROXIES."""
        if not self.enabled:
            logger.info("ProxyRotator: USE_PROXY=False, operando sin proxy.")
            return

        raw = getattr(config, "MANUAL_PROXIES", []) or []
        self._proxies = [p.strip() for p in raw if isinstance(p, str) and p.strip()]

        if not self._proxies:
            logger.warning(
                "ProxyRotator: USE_PROXY=True pero MANUAL_PROXIES está vacío. "
                "Operando sin proxy."
            )
            self.enabled = False
            return

        self._cycle = itertools.cycle(self._proxies)
        self._current = next(self._cycle)
        self._uses_since_rotation = 0
        logger.info(
            f"ProxyRotator: cargados {len(self._proxies)} proxies, "
            f"rotación cada {self.rotation_every} usos."
        )

    def get_next(self) -> Optional[str]:
        """Devuelve el proxy actual; rota cada `rotation_every` llamadas."""
        if not self.enabled or not self._cycle:
            return None

        self._uses_since_rotation += 1
        if self._uses_since_rotation >= self.rotation_every:
            self._current = next(self._cycle)
            self._uses_since_rotation = 0
            logger.info(f"ProxyRotator: rotando a {self._mask(self._current)}")
        return self._current

    def force_rotate(self) -> Optional[str]:
        """Fuerza rotación inmediata (útil tras un ban o timeout)."""
        if not self.enabled or not self._cycle:
            return None
        self._current = next(self._cycle)
        self._uses_since_rotation = 0
        logger.info(f"ProxyRotator: rotación forzada → {self._mask(self._current)}")
        return self._current

    @staticmethod
    def _mask(proxy: Optional[str]) -> str:
        if not proxy:
            return "<none>"
        if "@" in proxy:
            scheme, rest = proxy.split("://", 1) if "://" in proxy else ("", proxy)
            _, host = rest.rsplit("@", 1)
            return f"{scheme + '://' if scheme else ''}***@{host}"
        return proxy
