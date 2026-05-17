import { SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { Header } from "@/components/layout/header";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // The root flex container is pinned to the viewport (`h-screen`),
  // while the inner column uses `min-h-0` on `<main>` so its
  // `overflow-auto` actually activates. Without `min-h-0` a flex child
  // refuses to shrink below its content size, so the page below the
  // header simply overflows the viewport and the in-page scrollbar
  // never appears — that is BUG-18 from MANUAL_TESTING_REPORT.md
  // (password change section unreachable on the profile page).
  return (
    <SidebarProvider>
      <div className="flex h-screen w-full overflow-hidden">
        <AppSidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Header />
          <main className="min-h-0 flex-1 overflow-y-auto p-6">{children}</main>
        </div>
      </div>
    </SidebarProvider>
  );
}
