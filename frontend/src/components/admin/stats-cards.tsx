"use client";

import {
  Users,
  FileText,
  Database,
  Clock,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface StatsCardsProps {
  totalUsers: number;
  pendingTeachers: number;
  totalDocuments: number;
  totalChunks: number;
  isLoading: boolean;
}

export function StatsCards({
  totalUsers,
  pendingTeachers,
  totalDocuments,
  totalChunks,
  isLoading,
}: StatsCardsProps) {
  const t = useTranslations("admin.stats");

  const cards = [
    {
      title: t("users"),
      value: totalUsers,
      icon: Users,
      description: t("usersDescription"),
    },
    {
      title: t("pendingTeachers"),
      value: pendingTeachers,
      icon: Clock,
      description: t("pendingTeachersDescription"),
    },
    {
      title: t("documents"),
      value: totalDocuments,
      icon: FileText,
      description: t("documentsDescription"),
    },
    {
      title: t("chunks"),
      value: totalChunks,
      icon: Database,
      description: t("chunksDescription"),
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
            <card.icon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <>
                <div className="text-2xl font-bold">{card.value}</div>
                <p className="text-xs text-muted-foreground">
                  {card.description}
                </p>
              </>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
