import asyncio
import functools
import socket

import tqdm
from dns.resolver import Resolver

import config
from common import utils
from config import logger


def dns_resolver():
    """
    dns解析器
    """
    resolver = Resolver()
    resolver.nameservers = config.resolver_nameservers
    resolver.timeout = config.resolver_timeout
    resolver.lifetime = config.resolver_lifetime
    return resolver


async def dns_query_a(hostname):
    """
    查询A记录

    :param str hostname: 主机名
    :return: 查询结果
    """
    resolver = dns_resolver()
    try:
        answer = resolver.query(hostname, 'A')
    except Exception as e:
        logger.log('TRACE', e.args)
        answer = e
    return hostname, answer


async def aiodns_query_a(hostname):
    """
    异步查询A记录

    :param str hostname: 主机名
    :return: 查询结果
    """
    try:
        loop = asyncio.get_event_loop()
        socket.setdefaulttimeout(20)
        # answer = await loop.getaddrinfo(hostname, 80)
        answer = await loop.run_in_executor(None,
                                            socket.gethostbyname_ex,
                                            hostname)
    except BaseException as e:
        logger.log('TRACE', e.args)
        answer = e
    return hostname, answer


def resolve_callback(future, index, datas):
    """
    解析结果回调处理

    :param future: future对象
    :param index: 下标
    :param datas: 结果集
    """
    hostname, answer = future.result()
    if isinstance(answer, BaseException):
        logger.log('TRACE', answer.args)
        name = utils.get_classname(answer)
        datas[index]['reason'] = name + ' ' + str(answer)
        datas[index]['valid'] = 0
    elif isinstance(answer, tuple):
        ips = answer[2]
        datas[index]['ips'] = str(ips)[1:-1]


async def bulk_query_a(datas):
    """
    批量查询A记录

    :param datas: 待查的数据集
    :return: 查询过得到的结果集
    """
    logger.log('INFOR', '正在异步查询子域的A记录')
    tasks = []
    # semaphore = asyncio.Semaphore(config.limit_resolve_conn)
    for i, data in enumerate(datas):
        if not data.get('ips'):
            subdomain = data.get('subdomain')
            task = asyncio.ensure_future(aiodns_query_a(subdomain))
            wrapped_callback = functools.partial(resolve_callback,
                                                 index=i,
                                                 datas=datas)
            task.add_done_callback(wrapped_callback)  # 回调
            tasks.append(task)
    if tasks:  # 任务列表里有任务不空时才进行解析
        futures = asyncio.as_completed(tasks)
        for future in tqdm.tqdm(futures,
                                total=len(tasks),
                                desc='Progress',
                                ncols=60):
            await future
        # await asyncio.wait(tasks)  # 等待所有task完成
    logger.log('INFOR', '完成异步查询子域的A记录')
    return datas


def run_bulk_query(datas):
    new_datas = asyncio.run(bulk_query_a(datas))
    return new_datas
