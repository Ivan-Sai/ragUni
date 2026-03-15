"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { useTranslations } from "next-intl";
import { MessageSquare, FileText, Users, LayoutDashboard } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from "@/components/ui/sidebar";
import { ChatHistoryList } from "@/components/chat/chat-history-list";
import { useChatHistory } from "@/hooks/use-chat-history";

interface AppSidebarProps {
  activeSessionId?: string | null;
}

export function AppSidebar({ activeSessionId = null }: AppSidebarProps) {
  const t = useTranslations("layout.sidebar");
  const router = useRouter();
  const { data: session } = useSession();

  const userNavItems = [
    { title: t("chat"), href: "/chat", icon: MessageSquare },
  ];

  const adminNavItems = [
    { title: t("adminPanel"), href: "/admin", icon: LayoutDashboard },
    { title: t("documents"), href: "/admin/documents", icon: FileText },
    { title: t("users"), href: "/admin/users", icon: Users },
  ];
  const isAdmin = session?.user?.role === "admin";
  const token = session?.accessToken || "";

  const { sessions, isLoading, deleteSession } = useChatHistory({ token });

  function handleNewChat() {
    router.push("/chat");
  }

  return (
    <Sidebar>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>{t("navigation")}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {userNavItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton render={<Link href={item.href} />}>
                    <item.icon className="h-4 w-4" />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <ChatHistoryList
          sessions={sessions}
          isLoading={isLoading}
          activeSessionId={activeSessionId}
          onDelete={deleteSession}
          onNewChat={handleNewChat}
        />

        {isAdmin && (
          <SidebarGroup>
            <SidebarGroupLabel>{t("admin")}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {adminNavItems.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton render={<Link href={item.href} />}>
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
    </Sidebar>
  );
}
