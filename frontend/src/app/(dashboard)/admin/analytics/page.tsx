"use client";

import { useSession } from "next-auth/react";
import { useTranslations } from "next-intl";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminAnalytics } from "@/hooks/use-admin-analytics";

export default function AnalyticsPage() {
  const { data: session } = useSession();
  const t = useTranslations("admin.analytics");
  const token = session?.accessToken || "";

  const { data, isLoading, error } = useAdminAnalytics({ token });

  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <div className="grid gap-4 md:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-4">{t("title")}</h1>
        <p className="text-destructive">{error ? t("loadError") : t("noData")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-bold">{t("title")}</h1>

      {/* Stats cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t("queriesForPeriod")}</CardDescription>
            <CardTitle className="text-3xl">{data.total_queries}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t("logins")}</CardDescription>
            <CardTitle className="text-3xl">{data.total_logins}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t("documentUploads")}</CardDescription>
            <CardTitle className="text-3xl">{data.total_uploads}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t("avgResponseTime")}</CardDescription>
            <CardTitle className="text-3xl">
              {data.avg_response_time ? `${data.avg_response_time}${t("seconds")}` : "\u2014"}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Queries per day chart */}
      <Card>
        <CardHeader>
          <CardTitle>{t("queriesPerDay")}</CardTitle>
        </CardHeader>
        <CardContent>
          {data.queries_per_day.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.queries_per_day}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={12} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted-foreground text-center py-8">
              {t("noDataForPeriod")}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Active users per day chart */}
      <Card>
        <CardHeader>
          <CardTitle>{t("activeUsersPerDay")}</CardTitle>
        </CardHeader>
        <CardContent>
          {data.active_users_per_day.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data.active_users_per_day}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={12} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted-foreground text-center py-8">
              {t("noDataForPeriod")}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
