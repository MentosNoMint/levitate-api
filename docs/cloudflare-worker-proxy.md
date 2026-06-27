# Настройка Cloudflare Worker прокси для обхода блокировок Google

Поскольку сервер находится в регионе, где Google Cloud Gemini API недоступен, запросы возвращают ошибку `User location is not supported`. 
Мы решим это, создав бесплатный Cloudflare Worker, который будет выступать в роли прокси (все запросы от Cloudflare идут с разрешенных IP-адресов США/Европы).

---

## Шаг 1. Создание Cloudflare Worker

1. Зарегистрируйся или войди на [Cloudflare](https://dash.cloudflare.com/).
2. В левом меню выбери **Workers & Pages** -> **Overview**.
3. Нажми кнопку **Create** (или **Create application**), затем выбери **Worker** (или **Create Worker**).
4. Дай воркеру любое имя (например, `google-api-proxy`) и нажми **Deploy**.
5. После деплоя нажми кнопку **Edit Code** (Редактировать код).

---

## Шаг 2. Код Воркера

Удали весь стандартный код и вставь этот универсальный скрипт:

```javascript
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // Парсим путь для определения целевого хоста Google
    const pathParts = url.pathname.split('/');
    let targetHost = 'daily-cloudcode-pa.googleapis.com';
    
    if (pathParts[1] && pathParts[1].endsWith('googleapis.com')) {
      targetHost = pathParts[1];
      url.pathname = '/' + pathParts.slice(2).join('/');
    }
    
    url.hostname = targetHost;
    url.protocol = 'https:';
    url.port = '';

    // Копируем и модифицируем заголовки
    const headers = new Headers(request.headers);
    headers.set('Host', targetHost);
    
    if (headers.has('Origin')) {
      headers.set('Origin', `https://${targetHost}`);
    }

    const newRequest = new Request(url.toString(), {
      method: request.method,
      headers: headers,
      body: request.body,
      redirect: 'manual'
    });

    return fetch(newRequest);
  },
};
```

Нажми **Save and deploy** (Сохранить и развернуть) в правом верхнем углу.

---

## Шаг 3. Получение ссылки

После сохранения ты получишь адрес воркера, например:
```
https://google-api-proxy.<твое-имя>.workers.dev
```

---

## Шаг 4. Настройка на сервере

1. Подключись к серверу по SSH.
2. Открой файл конфигурации `.env`:
   ```bash
   nano /opt/levitate-api/.env
   ```
3. Найди параметр `ANTIGRAVITY_CLOUD_CODE_ENDPOINT` и замени его значение, добавив имя хоста Google в путь:
   ```env
   ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://google-api-proxy.<твое-имя>.workers.dev/daily-cloudcode-pa.googleapis.com
   ```
   *(Замени `https://google-api-proxy.<твое-имя>.workers.dev` на реальную ссылку твоего воркера)*.

4. Перезапусти контейнер бэкенда, чтобы применить настройки:
   ```bash
   cd /opt/levitate-api
   docker compose up -d backend
   ```

---

## Как это работает

Бэкенд отправляет запрос на твой Cloudflare Worker. Воркер видит в пути `daily-cloudcode-pa.googleapis.com`, перенаправляет запрос туда от своего лица (из поддерживаемого региона) и возвращает ответ твоему бэкенду.
