# Cloudflare Worker: прокси Cloud Code API (обход geo-блокировки)

## Зачем

Сервер в регионе, где Google Cloud Code / Gemini API недоступен, получает ошибки вроде:

- `User location is not supported`
- `not available in your country`

Cloudflare Worker принимает запросы с вашего сервера и проксирует их на `*.googleapis.com` с IP Cloudflare (США/Европа). OAuth (`oauth2.googleapis.com`) **не** проксируется — из РФ он обычно работает напрямую.

Levitate использует один env:

```env
ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://<worker-url>/daily-cloudcode-pa.googleapis.com
```

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
 * Client:
 *   ANTIGRAVITY_CLOUD_CODE_ENDPOINT=https://<worker>/daily-cloudcode-pa.googleapis.com
 *
 * Examples:
 *   /daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels
 *   /daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse
 *   /cloudcode-pa.googleapis.com/v1internal:loadCodeAssist
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
  let host = "daily-cloudcode-pa.googleapis.com";
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

Формат обязателен: **base URL воркера + `/daily-cloudcode-pa.googleapis.com` в пути** (path-style host embedding).

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

Это хорошо: запрос дошёл до Google, а не упёрся в geo-блок. Geo-ошибка / HTML от блокировки / `host not allowed` — плохо.

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
  → POST https://<worker>/daily-cloudcode-pa.googleapis.com/v1internal:...
    → Worker парсит host из первого сегмента пути
    → fetch https://daily-cloudcode-pa.googleapis.com/v1internal:...
    → стрим/ответ обратно в Levitate
```

Связанный гайд по добавлению Google-аккаунтов: [ssh-tunnel-guide.md](./ssh-tunnel-guide.md).

---

## Известная проблема: intermittent `User location is not supported`

Даже при корректном Worker (health = `ok`, unauth path = `401 UNAUTHENTICATED`) Google иногда отвечает:

```json
{"error":{"code":400,"message":"User location is not supported for the API use.","status":"FAILED_PRECONDITION"}}
```

Наблюдения с production-сервера Levitate:

1. Прямой вызов `https://daily-cloudcode-pa.googleapis.com/...` с RU-сервера — **всегда** LOCATION 400.
2. Через Worker — **~50%** LOCATION / **~50%** OK на одном и том же payload/токене.
3. Worker colo (cf-ray `…-ARN`) один и тот же; Google по-разному классифицирует egress-IP Cloudflare.
4. `fetchAvailableModels` / квоты обычно проходят; падает именно `streamGenerateContent`.

### Что делает Levitate backend

- Ретраит geo/LOCATION до 5 раз с коротким backoff на том же credential.
- Классифицирует ошибку как transient (не reauth / не exhausted).
- В логах пишет `endpoint=` чтобы было видно, что запрос шёл через Worker, а не напрямую.

### Что можно улучшить в Cloudflare Dashboard (вручную)

1. **Workers → ваш worker → Settings → Triggers / Domains**  
   Привяжите **кастомный домен** на зоне Cloudflare (не только `*.workers.dev`) — иногда меняет egress-путь.
2. **Smart Placement** (если доступен на плане): Settings → Placement → Smart / regional closer to Google US.  
   На `workers.dev` free-плане colo выбирается близко к клиенту (сервер → ARN/EU), и часть CF egress-IP Google считает «unsupported».
3. Если LOCATION остаётся частым (>10–20% после ретраев backend): поднимите **маленький VPS в US/DE** как reverse-proxy на `daily-cloudcode-pa.googleapis.com` и укажите его URL в `ANTIGRAVITY_CLOUD_CODE_ENDPOINT` (path-style тот же). Worker CF — не единственный вариант.
4. Код Worker из этого гайда (стрип `CF-*` / `X-Forwarded-*`) должен быть задеплоен как есть. Naive passthrough снова утечёт RU.

Проверка после изменений:

```bash
# с сервера / из backend-контейнера — серия generate через worker
# ожидаемо: большинство 200; одиночные LOCATION допустимы (backend ретраит)
```
