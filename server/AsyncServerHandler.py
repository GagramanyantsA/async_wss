import asyncio
import uuid
import json

from typing import Dict, Tuple, Optional

from logging import Logger

from websockets.exceptions import ConnectionClosedOK as WS_ConnectionClosedOK, \
    ConnectionClosedError as WS_ConnectionClosedError

from .SecuredWebsocketServerProtocol import SecuredWebsocketServerProtocol
from .ClientsControllerBase import ClientsControllerBase


class AsyncServerHandler:

    def __init__(self, clients_controller: ClientsControllerBase,
                 logger: Logger,
                 exception_queue: asyncio.Queue):
        self._name = 'AsyncWSHandler'.ljust(15)

        self._clients_controller = clients_controller
        self._logger = logger

        self._exception_queue = exception_queue

    @property
    def name(self):
        return self._name

    async def _process_data(self, client_id: str, websocket: SecuredWebsocketServerProtocol, json_obj: Dict):
        raise NotImplementedError()

    def _parse_message(self, message: str) -> Tuple[Optional[Dict], str]:
        try:
            json_obj = json.loads(message)
        except Exception as ex:
            return None, f'Unknown message: {message}. Reason: {str(ex)}'

        return json_obj, ''

    def _add_client(self, websocket: SecuredWebsocketServerProtocol) -> Tuple[str, str]:
        client_id = str(uuid.uuid4())
        client_ip = websocket.client_ip

        self._clients_controller.add_new_client(client_id, websocket)
        clients_amount = self._clients_controller.get_clients_amount()

        self._logger.debug(f'{self.name} New Client Connected '
                           f'[Uuid: {client_id}][IP: {client_ip}][Clients Amount: {clients_amount}]')

        return client_id, client_ip

    def _remove_client(self, client_id: str, client_ip: str):
        self._clients_controller.remove_client(client_id)
        clients_amount = self._clients_controller.get_clients_amount()

        self._logger.debug(f'{self.name} Client Disconnecting '
                           f'[Uuid: {client_id}][IP: {client_ip}][Clients Amount: {clients_amount}]')

    async def do_action(self, websocket: SecuredWebsocketServerProtocol, path: str):
        try:
            client_id, client_ip = self._add_client(websocket)
        except Exception as ex:
            self._logger.exception(ex)
            await self._exception_queue.put((self.name, 'Adding Connected Client', ex))
            return

        while True:
            try:
                message = await websocket.recv()
                self._logger.debug(f'{self.name} R < {message}')

                json_obj, err = self._parse_message(message)

                if err:
                    self._logger.warning(f'{self.name} parse message error: {err}')
                    continue

                await self._process_data(client_id, websocket, json_obj)

            except WS_ConnectionClosedOK as ex:
                self._logger.debug(f'{self.name} Client [Id:{client_id}] Disconnected! Reason: {str(ex)}')
                break

            except WS_ConnectionClosedError as ex:
                self._logger.debug(f'{self.name} Client [Id:{client_id}] Disconnected! Reason: {str(ex)}')
                break

            except Exception as ex:
                self._logger.exception(ex)
                await self._exception_queue.put((self.name, 'Processing Message', ex))
                break

        try:
            self._remove_client(client_id, client_ip)
        except Exception as ex:
            self._logger.exception(ex)
            await self._exception_queue.put((self.name, 'Removing Disconnected Client', ex))
