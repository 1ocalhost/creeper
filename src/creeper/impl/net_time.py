import datetime
import email.utils
import httpx


async def get_net_time():
    async with httpx.AsyncClient() as session:
        resp = await session.head('http://www.baidu.com')

    date = resp.headers['Date']
    server_datetime = email.utils.parsedate_to_datetime(date)
    server_time = datetime.datetime.timestamp(server_datetime)

    return server_time
