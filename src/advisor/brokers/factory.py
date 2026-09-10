from __future__ import annotations

import logging

from ..config import Config
from .angelone import AngelOneClient
from .base import BrokerClient, BrokerError
from .upstox import UpstoxClient
from .zerodha import ZerodhaClient

log = logging.getLogger(__name__)

_CLIENTS = {"zerodha": ZerodhaClient, "upstox": UpstoxClient, "angelone": AngelOneClient}


def build_brokers(
    cfg: Config,
    creds_override: dict[str, dict] | None = None,
) -> list[BrokerClient]:
    """Instantiate and connect every enabled broker.

    Env mode (default): uses cfg.brokers + cfg.creds (shared deployment).
    Multi-user mode: pass creds_override = {"zerodha": {...}, ...} straight from
    the user's decrypted BrokerCredential rows. Connection failures are logged
    and skipped so one dead token doesn't sink the whole run.
    """
    if creds_override is not None:
        source = creds_override
        names = list(creds_override)
    else:
        source = {
            "zerodha": cfg.creds.zerodha,
            "upstox": cfg.creds.upstox,
            "angelone": cfg.creds.angelone,
        }
        names = cfg.brokers

    clients: list[BrokerClient] = []
    for name in names:
        cls = _CLIENTS.get(name)
        if cls is None:
            log.warning("unknown broker %r, skipping", name)
            continue
        try:
            c = cls(**source.get(name, {}))
            c.connect()
            clients.append(c)
            log.info("connected broker: %s", name)
        except BrokerError as e:
            log.error("skipping %s: %s", name, e)
        except TypeError as e:
            log.error("skipping %s: bad credential fields (%s)", name, e)
        except Exception as e:  # noqa: BLE001
            log.exception("skipping %s (unexpected): %s", name, e)
    return clients
