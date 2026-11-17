import { createElement } from "react";
import { BarChart3, Bot, Code2, Compass, FileText, Image, Search } from "lucide-react";

// One icon per agent (lucide, decorative: the label next to it carries the meaning).
export const AGENT_ICONS = {
  root: Compass,
  general: Bot,
  code: Code2,
  data: BarChart3,
  research: Search,
  document: FileText,
  image: Image,
};

export function agentIcon(name, size = 16) {
  return createElement(AGENT_ICONS[name] || Bot, { size, "aria-hidden": true, className: "icon", strokeWidth: 2 });
}

export function agentLabel(agents, name) {
  if (name === "root") return "Router";
  return agents?.find((a) => a.name === name)?.label || (name ? name[0].toUpperCase() + name.slice(1) : "Assistant");
}

/** Human-readable live status, e.g. "Data Agent: table info". Plain text (used in aria-live). */
export function describeStatus(agents, status) {
  if (!status) return "Assistant is responding...";
  const who = agentLabel(agents, status.agent);
  if (status.status === "routing") return "Choosing the best agent...";
  if (status.status === "waiting") return `${who} is waiting for the provider (rate limit)...`;
  if (status.status === "tool") return `${who}: ${status.tool.replaceAll("_", " ")}...`;
  return `${who} is working...`;
}
