import config from "@ecommerce/config/next";

export default config.createNextConfig({
  appDirectory: import.meta.dirname,
  zonePath: "/admin",
});
