# Cloudflare Worker: прокси Cloud Code API (обход geo-блокировки)

## Зачем

Сервер в регионе, где Google Cloud Code / Gemini API недоступен, может получать ошибки вроде:

- `User location is not supported`
- `not available in your country`

Cloudflare Worker принимает запросы с вашего сервера и отправляет их к `*.googleapis.com` через egress Cloudflare. Это снижает зависимость от location сервера, но не является постоянной гарантией.

Для текущего production рекомендуется path-style endpoint:

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://<worker-url>/cloudcode-pa.googleapis.com
```

`/daily-cloudcode-pa.googleapis.com` остаётся поддерживаемой альтернативой allowlist, но сейчас не рекомендуется для production из-за наблюдавшейся intermittent geo-классификации.

Бэкенд собирает URL как `{ANTIGRAVITY_CLOUD_CODE_ENDPOINT}/v1internal:...`.

---

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
 *   ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://<worker>/cloudcode-pa.googleapis.com
 *
 * Examples:
 *   /cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels
 *   /cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse
 *   /daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist (supported alternative)
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

Формат: **base URL воркера + `/cloudcode-pa.googleapis.com` в пути** (path-style host embedding).

Рекомендуемый production endpoint:

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://<worker-url>/cloudcode-pa.googleapis.com
```

Пример:

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://antigravity.<account>.workers.dev/cloudcode-pa.googleapis.com
```

Реальный production-пример (подставьте свой аккаунт/имя):

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://antigravity.artemkiselev18072k6.workers.dev/cloudcode-pa.googleapis.com
```

`/daily-cloudcode-pa.googleapis.com` поддерживается allowlist как альтернативный path, но для текущего production не рекомендуется. Если нужно временно проверить его, замените только значение env и повторите аутентифицированные проверки из шага 5.

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

Вывод: generate на `cloudcode-pa` сейчас мёртв независимо от IP. Generate на `daily-cloudcode-pa` жив, но Google режет RU/ARN. Worker, вызванный с VPS, садится в colo **ARN**; с этой машины — **FRA**. Чтобы daily работал с Levitate на Beget, Worker должен egress-ить из поддерживаемого colo (Smart Placement / западный прокси), иначе путь VPS→ARN→daily снова даст 400.

Backend после 429/geo на одном host пробует sibling (`cloudcode-pa` ↔ `daily-cloudcode-pa`).

### Точная диагностика

1. Сначала выполните **аутентифицированный** запрос на текущем endpoint; используйте `gemini-3.6-flash-high` и проверьте HTTP-статус и тело ответа.
2. Если появляется `FAILED_PRECONDITION` / `User location is not supported`, замените только `ANTIGRAVITY_CLOUD_CODE_ENDPOINT` на рекомендуемый `/cloudcode-pa.googleapis.com`.
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
