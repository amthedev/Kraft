import redis as redis_lib
import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.config import settings

# SquareCloud Redis usa SSL self-signed — cria client com ssl_cert_reqs=None
_url = settings.redis_url
if _url.startswith("rediss://"):
    _client = redis_lib.from_url(
        _url,
        ssl_cert_reqs=None,
        socket_connect_timeout=10,
        socket_timeout=30,
        decode_responses=False,
    )
else:
    _client = redis_lib.from_url(_url, decode_responses=False)

broker = RedisBroker(client=_client)
dramatiq.set_broker(broker)
