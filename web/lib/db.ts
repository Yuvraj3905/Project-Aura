import { Pool } from "pg";

// Single shared connection pool for app queries (NOT for LISTEN — see lib/notify.ts).
export const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 10,
});
