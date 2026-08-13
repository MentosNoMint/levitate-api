/**
 * Antigravity / Cloud Code API reverse proxy (single worker).
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
    // Placement check helper. Cloudflare adds the `cf-placement` header to
    // the REQUEST when placement is enabled ("remote-LHR" = moved to London
    // colo, "local-EWR" = ran in the default eyeball colo). The header is
    // NOT added to the client response automatically, so /trace echoes it
    // in both the JSON body and a response header.
    if (url.pathname === "/trace") {
      const cfPlacement = request.headers.get("cf-placement");
      const payload = {
        eyeballColo: request.cf?.colo ?? null,
        eyeballCountry: request.cf?.country ?? null,
        eyeballRegion: request.cf?.region ?? null,
        cfPlacement: cfPlacement,
      };
      const headers = { "content-type": "application/json" };
      if (cfPlacement) {
        headers["cf-placement"] = cfPlacement;
      }
      return new Response(JSON.stringify(payload), { headers });
    }
    // /cdn-cgi/* is Cloudflare control plane, not a proxied Google path.
    // Serving it via parseTarget would forward it upstream and make
    // /cdn-cgi/trace a misleading "placement check".
    if (url.pathname.startsWith("/cdn-cgi/")) {
      return Response.json({ error: "cdn-cgi paths are not proxied" }, { status: 404 });
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
