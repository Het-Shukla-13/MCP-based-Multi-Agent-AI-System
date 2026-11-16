export const AGENT_ICONS = {
  root: "🧭",
  general: "🤖",
  code: "💻",
  data: "📊",
  research: "🔍",
  document: "📄",
  image: "🖼️",
};

export const agentIcon = (name) => AGENT_ICONS[name] || "🤖";

export function agentLabel(agents, name) {
  if (name === "root") return "Router";
  return agents?.find((a) => a.name === name)?.label || (name ? name[0].toUpperCase() + name.slice(1) : "Assistant");
}

/** Human-readable live status, e.g. "Data Agent → table_info". */
export function describeStatus(agents, status) {
  if (!status) return "Assistant is responding...";
  const who = `${agentIcon(status.agent)} ${agentLabel(agents, status.agent)}`;
  if (status.status === "routing") return "🧭 Choosing the best agent...";
  if (status.status === "tool") return `${who} → ${status.tool.replaceAll("_", " ")}...`;
  return `${who} is working...`;
}
