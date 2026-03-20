import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/analysis", label: "Analysis" },
  { to: "/live", label: "Live Monitor" },
  { label: "Data", header: true },
  { to: "/data/db", label: "Tracks" },
  { to: "/data/bridge", label: "Bridge" },
  { to: "/data/enrichment", label: "Enrichment" },
  { label: "System", header: true },
  { to: "/logs", label: "Logs" },
  { to: "/network", label: "Network" },
] as const;

export function Sidebar() {
  return (
    <nav className="w-48 shrink-0 border-r border-gray-800 bg-gray-950 py-4 flex flex-col gap-1">
      {navItems.map((item, i) => {
        if ("header" in item) {
          return (
            <div
              key={i}
              className="px-4 pt-4 pb-1 text-xs font-semibold uppercase tracking-wider text-gray-500"
            >
              {item.label}
            </div>
          );
        }
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `block px-4 py-1.5 text-sm transition-colors ${
                isActive
                  ? "bg-gray-800 text-white font-medium"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-900"
              }`
            }
          >
            {item.label}
          </NavLink>
        );
      })}
    </nav>
  );
}
