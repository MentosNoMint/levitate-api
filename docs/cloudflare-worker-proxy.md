# Cloudflare Worker: прокси Cloud Code API (обход geo-блокировки)

## Зачем

Сервер в регионе, где Google Cloud Code / Gemini API недоступен, может получать ошибки вроде:

- `User location is not supported`
- `not available in your country`

Cloudflare Worker принимает запросы с вашего сервера и отправляет их к `*.googleapis.com` через egress Cloudflare. Это снижает зависимость от location сервера, но не является постоянной гарантией.

Для текущего production рекомендуется path-style endpoint официального desktop generate:

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://<worker-url>/daily-cloudcode-pa.googleapis.com
```

`/cloudcode-pa.googleapis.com` остаётся в allowlist как sibling: тот же рабочий token на generate сейчас отвечает 429 RESOURCE_EXHAUSTED с FRA и ARN. Это не доказанная «перегрузка». Worker/daily с colo ARN флапает 200/400 location — backend ретраит тот же host, не прыгает сразу на cloudcode-pa.

Бэкенд собирает URL как `{ANTIGRAVITY_CLOUD_CODE_ENDPOINT}/v1internal:...`.

---

## Шаг 0. Текущее состояние и кандидат на постоянный egress

**Проверено (2026-08-13):** Worker, вызванный с Beget VPS, исполняется в colo **ARN**, и `streamGenerateContent` на `daily-cloudcode-pa` флапает `200/400 User location is not supported`. Нативная проба с VPS без локальных процессов: `[200, 400, 400, 200, 400]`. Geo-ретраи Levitate на том же daily-хосте добирают до 200: полный игровой ход прошёл с `source=live provider=arem` (158 слов) без прокси/туннелей на локальной машине.

**Кандидат на устранение флапа (НЕ проверен в проде):** явный `placement.region` в `worker/wrangler.toml` — Worker исполняется возле Google Cloud US, Google видит не-RU egress:

```toml
# worker/wrangler.toml
name = "antigravity"   # деплой поверх существующего воркера — URL в Levitate не меняется
main = "worker.js"
compatibility_date = "2026-01-22"

[placement]
region = "gcp:us-east4"
```

`name = "antigravity"` обязателен: деплой обновляет тот самый `antigravity.<account>.workers.dev`, иначе появится новый subdomain и Levitate придётся переключать endpoint. `placement.hostname` для этого НЕ использовать: host-probing экспериментален и ненадёжен против replicated/anycast-эндпоинтов вроде `googleapis.com`.

Деплой (нужен вход в Cloudflare):

```bash
cd worker
npx wrangler login   # один раз, откроет браузер Cloudflare
npx wrangler deploy
```

Обязательная верификация после деплоя, и только потом можно считать фикс работающим:

1. С VPS: `curl -sS -D- https://antigravity.<account>.workers.dev/trace` — JSON отдаёт eyeball-colo (`request.cf`), а заголовок ответа `cf-placement` показывает, где воркер реально исполняется; он должен присутствовать и не быть `local`/ARN. `cdn-cgi/trace` для проверки НЕ годится: воркер проксирует всё, кроме `/`, `/health` и `/trace`, поэтому `/cdn-cgi/*` он явно режет 404, а не отдаёт colo.
2. 10 подряд `streamGenerateContent` на daily — ни одного 400 location.
3. Полный игровой ход — `source=live provider=arem`.

Если 400 сохраняются — убрать блок `[placement]` и остаться на geo-ретраях или поднять выделенный западный прокси.

## Шаг 1. Создать Worker

1. Войдите в [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. **Workers & Pages** → **Overview** → **Create** → **Worker**.
3. Имя любое (`antigravity`, `google-api-proxy` и т.п.) → **Deploy**.
4. **Edit Code** — удалите шаблон и вставьте код ниже → **Save and Deploy**.

---

## Шаг 2. Код Worker (production)

```javascript
/**
 * Antigravity / Cloud Code API reverse proxy (single worker)
 *
 * Client (recommended):
 *   ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://<worker>/daily-cloudcode-pa.googleapis.com
 *
 * Examples:
 *   /daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse
 *   /daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels
 *   /cloudcode-pa.googleapis.com/v1internal:loadCodeAssist (sibling; generate currently 429s)
 *   /businessaicode.googleapis.com/v1/...   (optional enterprise)
 */

const ALLOWED_HOST_RE =
  /^(?:(?:daily-)?cloudcode-pa(?:\.sandbox)?\.googleapis\.com|businessaicode\.googleapis\.com|generativelanguage\.googleapis\.com)$/i;

const DROP_REQ = new Set([
  "host",
  "connection",
  "content-length",
  "transfer-encoding",
  "keep-alive",
  "proxy-connection",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "upgrade",
  // IP / geo leak — CRITICAL
  "cf-connecting-ip",
  "cf-ipcountry",
  "cf-ray",
  "cf-visitor",
  "cf-ew-via",
  "cf-worker",
  "cdn-loop",
  "true-client-ip",
  "x-real-ip",
  "x-forwarded-for",
  "x-forwarded-proto",
  "x-forwarded-host",
  "x-forwarded-port",
  "forwarded",
]);

const DROP_RES = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
]);

function allowedHost(host) {
  return ALLOWED_HOST_RE.test(host);
}

function parseTarget(url) {
  const parts = url.pathname.split("/").filter(Boolean);
  let host = "cloudcode-pa.googleapis.com";
  let rest = parts;

  if (parts[0] && parts[0].includes(".")) {
    host = parts[0];
    rest = parts.slice(1);
  }

  if (!allowedHost(host)) {
    return { error: `host not allowed: ${host}` };
  }

  const path = "/" + rest.join("/");
  return {
    host,
    target: `https://${host}${path}${url.search}`,
  };
}

function filterReqHeaders(src, host) {
  const h = new Headers();
  for (const [k, v] of src.entries()) {
    const lk = k.toLowerCase();
    if (DROP_REQ.has(lk) || lk.startsWith("cf-")) continue;
    h.set(k, v);
  }
  h.set("Host", host);
  h.set("Origin", `https://${host}`);
  if (h.has("Referer")) h.set("Referer", `https://${host}/`);
  return h;
}

function filterResHeaders(src) {
  const h = new Headers();
  for (const [k, v] of src.entries()) {
    if (DROP_RES.has(k.toLowerCase())) continue;
    h.set(k, v);
  }
  h.set("Access-Control-Allow-Origin", "*");
  h.set("Access-Control-Allow-Headers", "*");
  h.set("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS");
  h.set("Cache-Control", "no-cache");
  h.set("X-Accel-Buffering", "no");
  return h;
}

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Headers": "*",
          "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response(
        "ok antigravity-cloudcode-proxy\n",
        { headers: { "content-type": "text/plain; charset=utf-8" } }
      );
    }

    const parsed = parseTarget(url);
    if (parsed.error) {
      return Response.json({ error: parsed.error }, { status: 400 });
    }

    const headers = filterReqHeaders(request.headers, parsed.host);
    const init = {
      method: request.method,
      headers,
      redirect: "manual",
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : request.body,
    };
    // streaming POST body support on CF
    // @ts-ignore
    init.duplex = "half";

    let up;
    try {
      up = await fetch(parsed.target, init);
    } catch (e) {
      return Response.json(
        { error: "upstream_fetch_failed", detail: String(e), target: parsed.target },
        { status: 502 }
      );
    }

    return new Response(up.body, {
      status: up.status,
      statusText: up.statusText,
      headers: filterResHeaders(up.headers),
    });
  },
};
```

---

## Шаг 3. URL воркера

После деплоя в Dashboard появится `workers.dev` URL, например:

```text
https://antigravity.<account>.workers.dev
```

или

```text
https://google-api-proxy.<account>.workers.dev
```

Имя в subdomain — то, что вы задали при создании Worker.

---

## Шаг 4. `.env` на сервере

Формат: **base URL воркера + `/daily-cloudcode-pa.googleapis.com` в пути** (path-style host embedding, как у официального desktop).

Рекомендуемый production endpoint:

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://<worker-url>/daily-cloudcode-pa.googleapis.com
```

Пример:

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://antigravity.<account>.workers.dev/daily-cloudcode-pa.googleapis.com
```

Реальный production-пример (подставьте свой аккаунт/имя):

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://antigravity.artemkiselev18072k6.workers.dev/daily-cloudcode-pa.googleapis.com
```

`/cloudcode-pa.googleapis.com` остаётся sibling-fallback после исчерпания geo-ретраев daily. Не ставьте его primary для generate: тот же token отвечает 429.

Перезапуск только бэкенда:

```bash
cd /opt/levitate-api && docker compose up -d --force-recreate --no-deps backend
```

Для локальной разработки вне РФ можно оставить прямой URL:

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://daily-cloudcode-pa.googleapis.com
```

---

## Шаг 5. Проверка

### Health воркера

```bash
curl https://<worker-url>/health
```

Ожидаемый ответ:

```text
ok antigravity-cloudcode-proxy
```

### Доступ к Google через прокси (без токена)

С сервера или из контейнера:

```bash
curl -sS -X POST \
  "$ANTIGRAVITY_CLOUD_CODE_ENDPOINT/v1internal:fetchAvailableModels" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Ожидаемо: **HTTP 401 UNAUTHENTICATED** (или JSON с `UNAUTHENTICATED`).

Это подтверждает только маршрутизацию до Google через Worker. `401` без токена **не** доказывает успешную geo-классификацию; для этого нужна аутентифицированная проверка.

### Аутентифицированная проверка

Не записывайте токен в документацию или shell history. Используйте access token, который уже применяет backend, и тот же project ID/payload:

```bash
curl -sS -i -X POST \
  "$ANTIGRAVITY_CLOUD_CODE_ENDPOINT/v1internal:loadCodeAssist" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"cloudaicompanionProject\":\"${GOOGLE_USER_PROJECT:-levitate-api}\"}"
```

После этого выполните аутентифицированный chat-запрос через Levitate с моделью `gemini-3.6-flash-high`. Проверяйте HTTP-статус и тело ответа: `200` без `FAILED_PRECONDITION`/`User location is not supported` — полезнее, чем один health или unauthenticated `401`.

---

## Важные замечания

1. **Не проксируйте `oauth2.googleapis.com`.** OAuth из РФ обычно работает напрямую; этот Worker только для Cloud Code API.
2. **Стрип CF/geo-заголовков критичен.** Наивный passthrough утекает `CF-Connecting-IP`, `X-Forwarded-For`, `CF-IPCountry` и т.п. — Google снова видит RU-локацию. Код выше вычищает эти заголовки и подставляет `Host`/`Origin` целевого Google-хоста.
3. **SSE не буферизуйте.** Worker отдаёт `up.body` как есть + `Cache-Control: no-cache` / `X-Accel-Buffering: no`, чтобы `streamGenerateContent?alt=sse` стримился.
4. **Levitate нужен только один env** — `ANTIGRAVITY_CLOUD_CODE_ENDPOINT`. Остальные Google endpoints (OAuth) остаются прямыми.
5. **Allowlist хостов.** Worker принимает только `daily-cloudcode-pa`, `cloudcode-pa` (+ sandbox), `businessaicode`, `generativelanguage` на `googleapis.com`. Произвольные хосты → `400`.

---

## Как это стыкуется с Levitate

```text
Levitate backend
  → POST https://<worker>/cloudcode-pa.googleapis.com/v1internal:...
    → Worker парсит host из первого сегмента пути
    → fetch https://cloudcode-pa.googleapis.com/v1internal:...
    → стрим/ответ обратно в Levitate
```

Связанный гайд по добавлению Google-аккаунтов: [ssh-tunnel-guide.md](./ssh-tunnel-guide.md).

---

## cloudcode-pa vs daily-cloudcode-pa

Оба hostname относятся к одной внутренней семье Google Cloud Code API. Allowlist Worker принимает оба через regex `(?:daily-)?cloudcode-pa`. Google публично не описывает их точное operational distinction; любые толкования о роли `daily` — **[INFERENCE]**, а не официальная семантика.

Дискриминирующий тест (один access token, один сериализованный `streamGenerateContent`, без печати секретов), 2026-08-13:

| Host | Egress FRA / loc=PL | Egress ARN / loc=RU (Beget VPS) |
|---|---|---|
| `cloudcode-pa.googleapis.com` | **429 RESOURCE_EXHAUSTED** | **429 RESOURCE_EXHAUSTED** |
| `daily-cloudcode-pa.googleapis.com` | **200 generate** (`gemini-3.6-flash-high`) | **400 FAILED_PRECONDITION** `User location is not supported` |
| quota APIs (`loadCodeAssist`, `fetchAvailableModels`, `retrieveUserQuotaSummary`) | 200, remainingFraction 1.0, `standard-tier` | 200, same |

Replay официального desktop (credential, который сегодня даёт 200 в UI): тот же token+body 200 на worker/daily и 429 на cloudcode-pa. UA `2.4.3` vs `2.35.0` на worker/daily с VPS оба флапают 200/400 — User-Agent не отделяет 429. Worker с VPS остаётся colo **ARN**; с FRA-машины — **FRA**. ARN worker/daily может 200 без прокси этой машины, если backend ретраит тот же daily host.

Backend: location 400 ретраит тот же host; 429 пробует sibling. Не трактовать 429 как доказанную перегрузку.

### Точная диагностика

1. Сначала выполните **аутентифицированный** запрос на текущем endpoint; используйте `gemini-3.6-flash-high` и проверьте HTTP-статус и тело ответа.
2. Если появляется `FAILED_PRECONDITION` / `User location is not supported`, оставьте `/daily-cloudcode-pa.googleapis.com` и дайте geo-ретраям тот же host. Не переключайте primary на `/cloudcode-pa.googleapis.com` из-за location: generate там 429 на том же token.
3. Пересоздайте только backend:

   ```bash
   cd /opt/levitate-api && docker compose up -d --force-recreate --no-deps backend
   ```

4. Проверьте runtime env внутри контейнера, health Worker и затем повторите аутентифицированный chat-запрос:

   ```bash
   docker compose exec backend printenv ANTIGRAVITY_CLOUD_CODE_ENDPOINT
   curl https://<worker-url>/health
   ```

   Проверка через админскую симуляцию должна включать реальный authenticated chat, а не только открытие health URL.
5. Не считайте unauthenticated `401` признаком geo-успеха: он подтверждает только маршрутизацию до Google. Для результата нужны authenticated `loadCodeAssist`/`fetchAvailableModels` и chat.

### Rollback и fallback

Rollback делается изменением только значения `ANTIGRAVITY_CLOUD_CODE_ENDPOINT` без публикации токенов или других секретов, затем тем же пересозданием backend и полной проверкой runtime env, health и authenticated chat. Возврат на `/daily-cloudcode-pa.googleapis.com` — лишь временная проверка поддерживаемой альтернативы; результат нужно подтвердить заново.

Если у `/cloudcode-pa.googleapis.com` появятся persistent LOCATION-ошибки, надёжный fallback — стабильный reverse proxy на VPS в US/DE или другой фиксированный egress в разрешённом регионе. Ретраи Worker/backend — только mitigation, а не замена стабильному egress.
