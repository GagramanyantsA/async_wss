import asyncio

from logging import Logger

from server.AioRmqConsumer import AioRmqConsumer
from server.AsyncServer import AsyncServer
from server.AsyncServerHandler import AsyncServerHandler
from server.ClientsControllerBase import ClientsControllerBase
from server.Utils import Utils


class MainServerLoop:

    def __init__(self, name: str,
                 async_server: AsyncServer,
                 async_server_handler: AsyncServerHandler,
                 aio_rmq_consumer: AioRmqConsumer,
                 clients_controller: ClientsControllerBase,
                 logger: Logger,
                 exception_queue: asyncio.Queue):
        self._name: str = Utils.format_name(name)

        self._logger: Logger = logger
        self._exception_queue: asyncio.Queue = exception_queue

        self._async_server: AsyncServer = async_server
        self._async_server_handler: AsyncServer = async_server_handler
        self._aio_rmq_consumer: AioRmqConsumer = aio_rmq_consumer
        self._clients_controller: ClientsControllerBase = clients_controller

        self._loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

        self._exception_analysis_task: asyncio.Task = self._loop.create_task(self.exception_analysis(),
                                                                             name='Exc-Analysis-Task')
        self._runserver_task: asyncio.Task = self._loop.create_task(self._async_server.run(),
                                                                    name='Async-Server-Task')
        self._transport_consume_task: asyncio.Task = self._loop.create_task(self._aio_rmq_consumer.consume(),
                                                                            name='Transport-Consume-Task')
        self._check_clients_task: asyncio.Task = self._loop.create_task(self._clients_controller.check_clients(),
                                                                        name='Check-Clients-Task')

    @property
    def name(self) -> str:
        return self._name

    def run(self):
        self._loop.run_until_complete(self.main())

    def restart_to_cancel_tasks(self):
        def stop_loop():
            self._loop.stop()

        self._loop.call_later(1, stop_loop)
        self._loop.run_forever()

    def stop(self):
        self._loop.close()

    def cancel_all_tasks(self, with_exc_analysis_task: bool):
        exc_analysis_task_name = self._exception_analysis_task.get_name()

        for task in asyncio.all_tasks(self._loop):
            task_name = task.get_name()

            if not with_exc_analysis_task and task_name == exc_analysis_task_name:
                continue

            task.cancel()

        self._async_server.stop()

    async def exception_analysis(self):
        exc_analysis_name = Utils.format_name('Exception Analysis')

        self._logger.warning(f'{exc_analysis_name} Started')

        try:
            module_name, title, ex = await self._exception_queue.get()
            self._logger.critical(f'{module_name} | {title} | Exception: {ex}')
            self._logger.exception(ex)

            await asyncio.sleep(2)

            while not self._exception_queue.empty():
                module_name, title, ex = await self._exception_queue.get()
                self._logger.critical(f'{module_name} | {title} | Exception: {ex}')
                self._logger.exception(ex)

            self.cancel_all_tasks(with_exc_analysis_task=False)

        except asyncio.CancelledError:
            self._logger.warning(f'{exc_analysis_name} Stopped')

    async def main(self):
        await asyncio.wait([
            self._exception_analysis_task,
            self._runserver_task,
            self._check_clients_task,
            self._transport_consume_task
        ])
