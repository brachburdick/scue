import { Outlet } from "react-router-dom";
import { TopBar } from "./TopBar.tsx";
import { Sidebar } from "./Sidebar.tsx";
import { Console } from "./Console.tsx";

export function Shell() {
  return (
    <div className="h-screen flex flex-col">
      <TopBar />
      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <div className="flex-1 flex flex-col min-h-0">
          <main className="flex-1 overflow-y-auto p-6">
            <Outlet />
          </main>
          <Console />
        </div>
      </div>
    </div>
  );
}
