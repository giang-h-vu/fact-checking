import createClient from "openapi-fetch";
import type { paths } from "~/api";

const client = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE,
});

export default client;
