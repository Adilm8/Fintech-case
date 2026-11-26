export type AppMode = "demo" | "prod";

export const APP_MODE: AppMode =
  process.env.NEXT_PUBLIC_APP_MODE === "prod" ? "prod" : "demo";

export const IS_PROD = APP_MODE === "prod";
