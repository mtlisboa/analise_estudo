"""Run inside the web container to check idle channel delivery against Redis."""
import asyncio

from channels_redis.core import RedisChannelLayer
from django.conf import settings
import django

django.setup()


async def main():
    layer = RedisChannelLayer(
        **settings.CHANNEL_LAYERS['default']['CONFIG'],
        prefix='redis_idle_check',
    )
    channel = await layer.new_channel()
    pending = asyncio.create_task(layer.receive(channel))
    try:
        # Outlast redis-py 8's default socket timeout and Channels' blocking read.
        await asyncio.sleep(12)
        await layer.send(channel, {'type': 'idle.check'})
        assert await asyncio.wait_for(pending, 3) == {'type': 'idle.check'}
        print('PASS: notification delivered after 12 seconds idle')
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await layer.flush()
        await layer.close_pools()


asyncio.run(main())
