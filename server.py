import tornado.ioloop
import tornado.web
import tornado.websocket
import redis.asyncio as redis  # Асинхронный клиент Redis
import asyncio
import json
from datetime import datetime, timedelta

# Пул соединений Redis
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Таймаут для выхода из скрипта (в секундах)
IDLE_TIMEOUT = 300  # 5 минут
last_activity_time = datetime.now()  # Время последней активности

# Класс для WebSocket соединений
class ChatWebSocket(tornado.websocket.WebSocketHandler):
    clients = set()  # Хранит всех подключенных клиентов

    def check_origin(self, origin):
        """Разрешить все источники для WebSocket"""
        return True

    def open(self):
        """Когда клиент подключается"""
        global last_activity_time
        last_activity_time = datetime.now()  # Обновляем время активности
        ChatWebSocket.clients.add(self)
        self.write_message(json.dumps({"type": "system", "message": "Вы подключились к чату!"}))
        self.notify_clients()
        print("New client connected")

    def on_message(self, message):
        """Когда клиент отправляет сообщение"""
        global last_activity_time
        last_activity_time = datetime.now()  # Обновляем время активности
        asyncio.create_task(redis_client.publish('chat', message))  # Публикация сообщения в Redis

    def on_close(self):
        """Когда клиент отключается"""
        global last_activity_time
        last_activity_time = datetime.now()  # Обновляем время активности
        ChatWebSocket.clients.remove(self)
        self.notify_clients()
        print("Client disconnected")

    def notify_clients(self):
        """Отправка списка подключенных клиентов"""
        online_clients = len(ChatWebSocket.clients)
        for client in ChatWebSocket.clients:
            client.write_message(json.dumps({"type": "online", "clients": online_clients}))


# Функция для подписки на канал Redis
async def redis_subscriber():
    pubsub = redis_client.pubsub()  # Создаем pubsub
    await pubsub.subscribe("chat")  # Подписываемся на канал "chat"

    async for message in pubsub.listen():
        global last_activity_time
        last_activity_time = datetime.now()  # Обновляем время активности
        if message["type"] == "message":
            for client in ChatWebSocket.clients:
                await client.write_message(json.dumps({"type": "message", "content": message["data"]}))


# Функция для проверки таймаута
async def idle_timer():
    while True:
        await asyncio.sleep(5)  # Проверка каждые 5 секунд
        if (datetime.now() - last_activity_time) > timedelta(seconds=IDLE_TIMEOUT):
            print("Таймаут бездействия достигнут. Сервер завершает работу.")
            tornado.ioloop.IOLoop.current().stop()
            break


# Создание приложения Tornado
def make_app():
    return tornado.web.Application([
        (r"/ws", ChatWebSocket),  # Обработчик WebSocket
        (r"/(.*)", tornado.web.StaticFileHandler, {"path": ".", "default_filename": "index.html"}),  # Статика
    ])


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    print("Server started at http://localhost:8888")

    # Запуск Redis подписчика и idle таймера
    loop = asyncio.get_event_loop()
    loop.create_task(redis_subscriber())  # Запускаем Redis подписчик
    loop.create_task(idle_timer())       # Запускаем таймер простоя
    loop.run_forever()
