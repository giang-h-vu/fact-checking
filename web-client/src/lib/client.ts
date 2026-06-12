import createClient from "openapi-fetch";
import type { paths } from "~/api";

const AUTH_PREFIX = "/api/v1/auth/";

let refreshing: Promise<boolean> | null = null;

function tryRefresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

/**
 * Wraps fetch so that a 401 on any non-auth request triggers a single token
 * refresh and one retry. The request is cloned *before* sending so its body
 * survives for the retry.
 */
const fetchWithRefresh: typeof fetch = async (input, init) => {
  const request = new Request(input, init);
  const retryable = request.clone();
  const response = await fetch(request);

  if (response.status !== 401 || request.url.includes(AUTH_PREFIX)) {
    return response;
  }
  const refreshed = await tryRefresh();
  return refreshed ? fetch(retryable) : response;
};

const client = createClient<paths>({
  credentials: "include",
  fetch: fetchWithRefresh,
});

export default client;
